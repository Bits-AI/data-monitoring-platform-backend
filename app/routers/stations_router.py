from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.station import Station, Site, Logger, Sensor
from app.models.timeseries import TimeseriesData
from app.models.alert import Alert
from app.time_utils import to_myt_iso

router = APIRouter(tags=["Stations & Sites"])

class StationCreate(BaseModel):
    site_id: int
    name: str
    code: Optional[str] = None
    station_type: str = "Hydrology / Water Level"
    latitude: float
    longitude: float
    elevation: float = 0.0

class StationUpdate(BaseModel):
    name: Optional[str] = None
    station_type: Optional[str] = None
    logger_brand: Optional[str] = None
    logger_type: Optional[str] = None

class SensorUpdate(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = None
    visualizer_type: Optional[str] = None
    min_limit: Optional[float] = None
    max_limit: Optional[float] = None

@router.get("/sites")
def get_all_sites(db: Session = Depends(get_db)):
    sites = db.query(Site).filter(Site.is_active == True).all()
    return [
        {
            "id": s.id,
            "name": s.name,
            "code": s.code,
            "client_name": s.client_name or "JPS - WPKL",
            "description": s.description,
            "region": s.region,
            "latitude": s.latitude,
            "longitude": s.longitude,
            "station_count": len(s.stations)
        }
        for s in sites
    ]

@router.get("/stations")
def get_all_stations(
    site_id: Optional[int] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Station)
    if site_id:
        query = query.filter(Station.site_id == site_id)
    if status and status != "all":
        query = query.filter(Station.status == status)
    if search:
        s_term = f"%{search}%"
        query = query.filter((Station.name.ilike(s_term)) | (Station.code.ilike(s_term)))
    
    stations = query.all()
    result = []
    for st in stations:
        sensors_data = [
            {
                "id": s.id,
                "name": s.name,
                "metric_key": s.metric_key,
                "parameter_code": s.parameter_code or s.metric_key,
                "unit": s.unit,
                "visualizer_type": s.visualizer_type or "line",
                "current_value": s.current_value,
                "status": s.status,
                "min_limit": s.min_limit,
                "max_limit": s.max_limit,
                "last_reading_time": to_myt_iso(s.last_reading_time)
            }
            for s in st.sensors
        ]
        loggers_data = [
            {
                "id": l.id,
                "model": l.model,
                "serial_number": l.serial_number,
                "connection_type": l.connection_type,
                "status": l.status,
                "ip_address": l.ip_address
            }
            for l in st.loggers
        ]
        result.append({
            "id": st.id,
            "site_id": st.site_id,
            "site_name": st.site.name if st.site else "Unknown Site",
            "client_name": st.site.client_name if st.site else "NAHRIM",
            "name": st.name,
            "code": st.code,
            "station_type": st.station_type,
            "logger_brand": st.logger_brand or "Neon",
            "logger_type": st.logger_type or "Neon REST",
            "serial_number": st.serial_number or "",
            "latitude": st.latitude,
            "longitude": st.longitude,
            "elevation": st.elevation,
            "status": st.status,
            "battery_level": st.battery_level,
            "signal_strength": st.signal_strength,
            "solar_charging": st.solar_charging,
            "last_seen": to_myt_iso(st.last_seen),
            "sensors": sensors_data,
            "loggers": loggers_data
        })
    return result

@router.get("/stations/{station_id}")
def get_station_detail(station_id: int, db: Session = Depends(get_db)):
    st = db.query(Station).filter(Station.id == station_id).first()
    if not st:
        raise HTTPException(status_code=404, detail="Station not found")
    
    alerts = db.query(Alert).filter(Alert.station_id == station_id, Alert.status == "active").all()

    return {
        "id": st.id,
        "site_id": st.site_id,
        "site_name": st.site.name if st.site else "Unknown Site",
        "site_code": st.site.code if st.site else "",
        "client_name": st.site.client_name if st.site else "NAHRIM",
        "name": st.name,
        "code": st.code,
        "station_type": st.station_type,
        "logger_brand": st.logger_brand or "Neon",
        "logger_type": st.logger_type or "Neon REST",
        "serial_number": st.serial_number or "",
        "latitude": st.latitude,
        "longitude": st.longitude,
        "elevation": st.elevation,
        "status": st.status,
        "battery_level": st.battery_level,
        "signal_strength": st.signal_strength,
        "solar_charging": st.solar_charging,
        "last_seen": to_myt_iso(st.last_seen),
        "sensors": [
            {
                "id": s.id,
                "name": s.name,
                "metric_key": s.metric_key,
                "parameter_code": s.parameter_code or s.metric_key,
                "unit": s.unit,
                "visualizer_type": s.visualizer_type or "line",
                "current_value": s.current_value,
                "status": s.status,
                "min_limit": s.min_limit,
                "max_limit": s.max_limit,
                "last_reading_time": to_myt_iso(s.last_reading_time)
            }
            for s in st.sensors
        ],
        "loggers": [
            {
                "id": l.id,
                "model": l.model,
                "serial_number": l.serial_number,
                "firmware_version": l.firmware_version,
                "connection_type": l.connection_type,
                "ip_address": l.ip_address,
                "status": l.status
            }
            for l in st.loggers
        ],
        "active_alerts": [
            {
                "id": a.id,
                "metric_key": a.metric_key,
                "severity": a.severity,
                "message": a.message,
                "triggered_value": a.triggered_value,
                "created_at": to_myt_iso(a.created_at)
            }
            for a in alerts
        ]
    }

@router.patch("/stations/{station_id}")
def update_station(station_id: int, req: StationUpdate, db: Session = Depends(get_db)):
    st = db.query(Station).filter(Station.id == station_id).first()
    if not st:
        raise HTTPException(status_code=404, detail="Station not found")
    
    if req.name is not None:
        st.name = req.name
    if req.station_type is not None:
        st.station_type = req.station_type
    if req.logger_brand is not None:
        st.logger_brand = req.logger_brand
    if req.logger_type is not None:
        st.logger_type = req.logger_type
    
    db.commit()
    db.refresh(st)
    return {"message": "Station updated successfully", "station_id": st.id}

@router.patch("/stations/sensors/{sensor_id}")
def update_sensor(sensor_id: int, req: SensorUpdate, db: Session = Depends(get_db)):
    s = db.query(Sensor).filter(Sensor.id == sensor_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Sensor not found")
    
    if req.name is not None:
        s.name = req.name
    if req.unit is not None:
        s.unit = req.unit
    if req.visualizer_type is not None:
        s.visualizer_type = req.visualizer_type
    if req.min_limit is not None:
        s.min_limit = req.min_limit
    if req.max_limit is not None:
        s.max_limit = req.max_limit
    
    db.commit()
    db.refresh(s)
    return {"message": "Sensor updated successfully", "sensor_id": s.id}

@router.get("/stations/{station_id}/telemetry")
def get_station_telemetry(station_id: int, db: Session = Depends(get_db)):
    st = db.query(Station).filter(Station.id == station_id).first()
    if not st:
        raise HTTPException(status_code=404, detail="Station not found")
    
    sensors_dict = {
        s.metric_key: {
            "name": s.name,
            "value": s.current_value,
            "unit": s.unit,
            "visualizer_type": s.visualizer_type,
            "status": s.status,
            "timestamp": to_myt_iso(s.last_reading_time)
        }
        for s in st.sensors
    }

    return {
        "station_id": st.id,
        "station_name": st.name,
        "station_code": st.code,
        "status": st.status,
        "logger_brand": st.logger_brand or "Neon",
        "battery": st.battery_level,
        "signal_rssi": st.signal_strength,
        "solar_charging": st.solar_charging,
        "last_seen": to_myt_iso(st.last_seen),
        "metrics": sensors_dict
    }

@router.post("/stations")
def create_station(req: StationCreate, db: Session = Depends(get_db)):
    existing = db.query(Station).filter(Station.code == req.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Station code already exists")
    
    st = Station(
        site_id=req.site_id,
        name=req.name,
        code=req.code,
        station_type=req.station_type,
        latitude=req.latitude,
        longitude=req.longitude,
        elevation=req.elevation
    )
    db.add(st)
    db.commit()
    db.refresh(st)
    return {"message": "Station created successfully", "station_id": st.id}
