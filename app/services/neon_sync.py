import os
import re
import json
import logging
import threading
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.station import Site, Station, Logger, Sensor
from app.models.timeseries import TimeseriesData
from app.time_utils import now_myt_naive, to_myt_iso

logger = logging.getLogger("NeonSyncService")
db_lock = threading.Lock()

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOKEN_CACHE_FILE = os.path.join(BACKEND_ROOT, ".neon_token.json")
STATIONS_JSON_PATH = os.path.join(BACKEND_ROOT, "stations.json")

NEON_API_URL = os.getenv("NEON_API_URL", "https://restservice-neon.surechem.com.my:443/NeonRESTService.svc").rstrip("/")
NEON_USER = os.getenv("NEON_USER", "STARS")
NEON_PASSWORD = os.getenv("NEON_PASSWORD", "Abcd@1234")

PRESERVE_CAPS = {
    "ph": "pH",
    "battv": "BattV",
    "batt_v": "BattV",
    "orp": "ORP",
    "tds": "TDS",
    "tss": "TSS",
    "fm_upstream": "Flow Upstream",
    "fm_downstream": "Flow Downstream",
}

def clean_sql_identifier(raw_name: str) -> str:
    """Converts a string into a clean safe key identifier."""
    if not raw_name:
        return "val"
    s = re.sub(r'[^a-zA-Z0-9_]', '_', raw_name.strip())
    s = re.sub(r'_+', '_', s).strip('_').lower()
    if s and s[0].isdigit():
        s = f"metric_{s}"
    return s or "val"

def format_sensor_display_name(raw_name: str) -> str:
    """Formats sensor names cleanly for UI displays."""
    cleaned = raw_name.lower().strip()
    if cleaned in PRESERVE_CAPS:
        return PRESERVE_CAPS[cleaned]
    return raw_name.replace("_", " ").title()

def determine_default_visualizer(param_code: str, unit: str) -> str:
    """Assigns optimal chart visualizer type based on parameter name & unit."""
    param = param_code.lower().strip()
    u = unit.lower().strip()
    if any(k in param for k in ["rain", "rainfall", "precip"]) or u in ["mm", "inch"]:
        return "bar"
    if param == "ph":
        return "ph_scale"
    if any(k in param for k in ["battv", "batt_v", "battery", "vbat"]) or u in ["v", "volt", "mv"]:
        return "battery"
    if any(k in param for k in ["wind_dir", "winddir"]) or u in ["deg", "degree", "°"]:
        return "compass"
    return "line"

class NeonClient:
    def __init__(self, base_url: str = NEON_API_URL, user: str = NEON_USER, password: str = NEON_PASSWORD):
        self.base_url = base_url
        self.user = user
        self.password = password
        self._token: Optional[str] = None

    def get_token(self) -> str:
        if self._token:
            return self._token

        if os.path.exists(TOKEN_CACHE_FILE):
            try:
                with open(TOKEN_CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    tok = data.get("Token")
                    if tok:
                        self._token = tok
                        return self._token
            except Exception:
                pass

        return self._refresh_token()

    def _refresh_token(self) -> str:
        logger.info(f"Authenticating against Neon REST API at {self.base_url}...")
        resp = requests.get(
            f"{self.base_url}/GetSession",
            params={"u": self.user, "p": self.password},
            timeout=25,
        )
        resp.raise_for_status()
        new_token = resp.json().get("Token")
        if not new_token:
            raise RuntimeError("Failed to obtain session token from Neon REST API")
        self._token = new_token
        try:
            with open(TOKEN_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({"Token": new_token}, f)
        except Exception:
            pass
        return self._token

    def _get(self, endpoint: str, params: Optional[dict] = None) -> Any:
        url = f"{self.base_url}{endpoint}"
        headers = {"X-Authentication-Token": self.get_token()}
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        if resp.status_code == 401:
            logger.warning("Neon token expired (401). Refreshing token...")
            self._refresh_token()
            headers = {"X-Authentication-Token": self.get_token()}
            resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def get_nodes(self) -> List[Dict[str, Any]]:
        data = self._get("/GetNodeList")
        return data.get("GetNodeListResult", []) or []

    def get_channels(self, node_id: str) -> List[Dict[str, Any]]:
        data = self._get(f"/GetChannelList/{node_id}", params={"ShowInactive": "Inactive"})
        return data.get("GetChannelListResult", []) or []

    def get_samples(self, channel_id: int, start_time: str, end_time: str) -> List[Dict[str, Any]]:
        data = self._get(
            f"/GetData/{channel_id}",
            params={"StartTime": start_time, "EndTime": end_time, "DSTAdjust": "false"},
        )
        return (data or {}).get("GetDataResult", {}).get("Samples", []) or []

neon_api = NeonClient()

def load_stations_config() -> List[Dict[str, Any]]:
    if not os.path.exists(STATIONS_JSON_PATH):
        logger.warning(f"Stations configuration file not found at {STATIONS_JSON_PATH}")
        return []
    with open(STATIONS_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def sync_single_station(st_cfg: Dict[str, Any], days_lookback: int = 30) -> int:
    """
    Syncs metadata and timeseries readings for a single configured Neon station.
    """
    node_id = str(st_cfg.get("node_id", "")).strip()
    if not node_id:
        return 0

    custom_name = st_cfg.get("custom_name") or f"Neon Station {node_id}"
    station_code = None
    site_name = st_cfg.get("site_name") or "NAHRIM"
    client_name = st_cfg.get("client_name") or "NAHRIM"
    station_type = st_cfg.get("station_type") or "Hydrology & Meteorology"
    lat = float(st_cfg.get("latitude", 3.0135))
    lng = float(st_cfg.get("longitude", 101.7065))

    try:
        channels = neon_api.get_channels(node_id)
    except Exception as e:
        logger.error(f"[{custom_name}] Failed to fetch channels for Node {node_id}: {e}")
        return 0

    if not channels:
        logger.info(f"[{custom_name}] Node {node_id} has no channels.")
        return 0

    # Timeseries window
    now_utc = datetime.utcnow()
    start_utc = now_utc - timedelta(days=days_lookback)
    start_str = start_utc.strftime("%Y-%m-%dT00:00:00")
    end_str = now_utc.strftime("%Y-%m-%dT%H:%M:%S")
    # Timeseries window in Malaysia Time (MYT, UTC+8)
    now_myt = now_myt_naive()
    start_myt = now_myt - timedelta(days=days_lookback)
    start_str = start_myt.strftime("%Y-%m-%dT00:00:00")
    # Buffer 15 minutes into future so the very latest readings up to current minute are captured
    end_str = (now_myt + timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%S")

    # 1. Fetch channel readings over network (Outside DB lock!)
    channel_samples_data = {}
    for ch in channels:
        ch_id = ch.get("ID")
        raw_ch_name = ch.get("Name") or f"channel_{ch_id}"
        metric_key = clean_sql_identifier(raw_ch_name)
        try:
            samples = neon_api.get_samples(ch_id, start_str, end_str)
            # If no recent samples in window, try a wider fallback window up to 365 days
            if not samples:
                fallback_start = (now_utc - timedelta(days=365)).strftime("%Y-%m-%dT00:00:00")
                fallback_start = (now_myt - timedelta(days=365)).strftime("%Y-%m-%dT00:00:00")
                samples = neon_api.get_samples(ch_id, fallback_start, end_str)
            if not samples:
                # Deep historical check to ensure baseline data exists
                samples = neon_api.get_samples(ch_id, "2024-01-01T00:00:00", end_str)
            
            # Keep most recent 3000 samples per channel to keep queries agile
            if len(samples) > 3000:
                samples = samples[-3000:]

            channel_samples_data[ch_id] = (ch, metric_key, samples)
        except Exception as ex:
            logger.warning(f"[{custom_name}] Could not fetch samples for ch {ch_id} ({metric_key}): {ex}")

    total_samples_saved = 0

    # 2. Persist metadata & readings into database under lock
    with db_lock:
        db: Session = SessionLocal()
        try:
            # Site
            site = db.query(Site).filter(Site.name == site_name).first()
            if not site:
                site = Site(
                    name=site_name,
                    code="NAHRIM",
                    client_name=client_name,
                    description="Institut Penyelidikan Air Kebangsaan Malaysia (NAHRIM) Hydrological & Coastal Telemetry Array.",
                    region="Malaysia",
                    latitude=lat,
                    longitude=lng,
                    is_active=True
                )
                db.add(site)
                db.flush()
            else:
                site.client_name = client_name

            # Station
            station = db.query(Station).filter(
                (Station.serial_number == node_id) | (Station.name == custom_name)
            ).first()

            if not station:
                station = Station(
                    site_id=site.id,
                    name=custom_name,
                    code=station_code,
                    station_type=station_type,
                    latitude=lat,
                    longitude=lng,
                    logger_brand="Neon",
                    logger_type="Neon REST",
                    serial_number=node_id,
                    status="online",
                    battery_level=100.0,
                    signal_strength=-70,
                    solar_charging=True,
                    last_seen=now_myt
                )
                db.add(station)
                db.flush()
            else:
                station.name = custom_name
                station.code = station_code
                station.site_id = site.id
                station.station_type = station_type
                station.latitude = lat
                station.longitude = lng
                station.logger_brand = "Neon"
                station.logger_type = "Neon REST"
                station.serial_number = node_id

            # Logger record
            logger_rec = db.query(Logger).filter(Logger.station_id == station.id).first()
            if not logger_rec:
                logger_rec = Logger(
                    station_id=station.id,
                    model="Neon Remote Telemetry Unit",
                    serial_number=f"NEON-RTU-{node_id}",
                    connection_type="Cellular 4G / REST",
                    status="active",
                    last_heartbeat=now_myt
                )
                db.add(logger_rec)

            # Sensors
            sensor_records = {}
            for ch_id, (ch, metric_key, samples) in channel_samples_data.items():
                raw_ch_name = ch.get("Name") or f"channel_{ch_id}"
                raw_unit = (ch.get("Units") or "").strip()
                display_name = format_sensor_display_name(raw_ch_name)
                visualizer = determine_default_visualizer(metric_key, raw_unit)

                s = db.query(Sensor).filter(
                    Sensor.station_id == station.id,
                    Sensor.metric_key == metric_key
                ).first()

                if not s:
                    s = Sensor(
                        station_id=station.id,
                        name=display_name,
                        metric_key=metric_key,
                        unit=raw_unit or ("m" if "level" in metric_key else "val"),
                        sensor_type="Hydrological",
                        visualizer_type=visualizer,
                        parameter_code=metric_key,
                        status="normal"
                    )
                    db.add(s)
                    db.flush()
                else:
                    s.name = display_name
                    s.unit = raw_unit or s.unit
                    s.visualizer_type = visualizer
                sensor_records[ch_id] = s

            # Insert readings
            latest_station_ts = None
            for ch_id, (ch, m_key, samples) in channel_samples_data.items():
                s_obj = sensor_records.get(ch_id)
                if not s_obj or not samples:
                    continue

                existing_ts_rows = db.query(TimeseriesData.timestamp).filter(
                    TimeseriesData.station_id == station.id,
                    TimeseriesData.metric_key == m_key,
                    TimeseriesData.timestamp >= start_myt
                ).all()
                existing_ts_set = {r[0] for r in existing_ts_rows}

                new_records = []
                latest_val = None
                latest_ts = None

                for sp in samples:
                    ts_raw = sp.get("Time")
                    val_raw = sp.get("Value")
                    if not ts_raw or val_raw is None:
                        continue

                    try:
                        ts = datetime.strptime(ts_raw.split(".")[0], "%Y-%m-%dT%H:%M:%S")
                        val = float(val_raw)
                    except (ValueError, TypeError):
                        continue

                    if ts not in existing_ts_set:
                        new_records.append(TimeseriesData(
                            station_id=station.id,
                            sensor_id=s_obj.id,
                            metric_key=m_key,
                            value=val,
                            timestamp=ts,
                            quality_code="good"
                        ))
                        existing_ts_set.add(ts)

                    if latest_ts is None or ts > latest_ts:
                        latest_ts = ts
                        latest_val = val

                if new_records:
                    db.bulk_save_objects(new_records)
                    total_samples_saved += len(new_records)

                if latest_val is not None:
                    s_obj.current_value = latest_val
                    s_obj.last_reading_time = latest_ts
                    if "battery" in m_key:
                        station.battery_level = min(100.0, max(0.0, latest_val if latest_val <= 100.0 else (latest_val / 14.0) * 100.0))

                if latest_ts and (latest_station_ts is None or latest_ts > latest_station_ts):
                    latest_station_ts = latest_ts

            if latest_station_ts:
                station.last_seen = latest_station_ts
                diff_h = (now_myt - latest_station_ts).total_seconds() / 3600
                station.status = "online" if diff_h < 72 else "offline"

            db.commit()
            logger.info(f"[{custom_name}] Synced successfully. {total_samples_saved} new telemetry points.")
        except Exception as e:
            db.rollback()
            logger.error(f"[{custom_name}] Error during station sync: {e}")
        finally:
            db.close()

    return total_samples_saved

def run_neon_sync_all(days_lookback: int = 30, max_workers: int = 4):
    """
    Syncs configured Neon stations from stations.json.
    """
    stations_cfg = load_stations_config()
    logger.info(f"Loaded {len(stations_cfg)} stations from stations.json for Neon Sync.")

    total_synced = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(sync_single_station, cfg, days_lookback): cfg for cfg in stations_cfg}
        for future in as_completed(futures):
            cfg = futures[future]
            try:
                count = future.result()
                total_synced += count
            except Exception as e:
                logger.error(f"Error syncing station {cfg.get('custom_name')}: {e}")

    logger.info(f"Neon Sync Complete: {total_synced} total observations stored across {len(stations_cfg)} stations.")
    return total_synced
