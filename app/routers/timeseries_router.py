from datetime import datetime, timedelta
from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.timeseries import TimeseriesData
from app.models.station import Station, Sensor
from app.time_utils import now_myt_naive, to_myt_iso, to_myt_str

router = APIRouter(prefix="/timeseries", tags=["Telemetry & Time-Series"])

class PointEditRequest(BaseModel):
    value: float
    quality_code: Optional[str] = "corrected"
    remarks: Optional[str] = None
    edited_by: Optional[str] = "Hydrologist / Operator"

@router.get("/metrics")
def get_available_metrics(station_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(Sensor.metric_key, Sensor.name, Sensor.unit, Sensor.visualizer_type).distinct()
    if station_id:
        query = query.filter(Sensor.station_id == station_id)
    results = query.all()
    return [{"key": r[0], "name": r[1], "unit": r[2], "visualizer_type": r[3]} for r in results]

@router.get("/history")
def get_timeseries_history(
    station_id: int = Query(...),
    metric_key: Optional[str] = Query(None),
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(5000, ge=1, le=20000),
    db: Session = Depends(get_db)
):
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    # Use Malaysia Time (MYT, UTC+8) for cutoff calculation
    cutoff = now_myt_naive() - timedelta(hours=hours)
    query = db.query(TimeseriesData).filter(
        TimeseriesData.station_id == station_id,
        TimeseriesData.timestamp >= cutoff
    )
    if metric_key:
        query = query.filter(TimeseriesData.metric_key == metric_key)
    
    records = query.order_by(TimeseriesData.timestamp.asc()).limit(limit).all()

    # Fallback: if no records within cutoff window, fetch latest available records for historical stations
    if not records:
        fallback_query = db.query(TimeseriesData).filter(TimeseriesData.station_id == station_id)
        if metric_key:
            fallback_query = fallback_query.filter(TimeseriesData.metric_key == metric_key)
        records = fallback_query.order_by(TimeseriesData.timestamp.desc()).limit(min(limit, 300)).all()
        records.reverse()

    # Find sensor info
    sensors = db.query(Sensor).filter(Sensor.station_id == station_id).all()
    sensor_map = {
        s.metric_key: {
            "sensor_id": s.id,
            "name": s.name,
            "unit": s.unit,
            "visualizer_type": s.visualizer_type or "line"
        }
        for s in sensors
    }

    # Group by metric
    data_by_metric = {}
    for r in records:
        ts_iso = r.timestamp.isoformat()
        ts_iso = to_myt_iso(r.timestamp)
        if r.metric_key not in data_by_metric:
            data_by_metric[r.metric_key] = []
        raw_val = getattr(r, 'raw_value', None)
        is_edited = (raw_val is not None and abs(r.value - raw_val) > 1e-6) or (r.quality_code == "corrected")
        data_by_metric[r.metric_key].append({
            "id": r.id,
            "timestamp": ts_iso,
            "ts": ts_iso,
            "value": r.value,
            "raw_value": raw_val if raw_val is not None else r.value,
            "quality_code": r.quality_code or "good",
            "remarks": getattr(r, 'remarks', None),
            "is_edited": is_edited
        })

    series = []
    for m_key, pts in data_by_metric.items():
        meta = sensor_map.get(m_key, {
            "sensor_id": 0,
            "name": m_key,
            "unit": "",
            "visualizer_type": "line"
        })
        series.append({
            "sensor_id": meta["sensor_id"],
            "metric_key": m_key,
            "sensor_name": meta["name"],
            "name": meta["name"],
            "unit": meta["unit"],
            "visualizer_type": meta["visualizer_type"],
            "readings": pts,
            "points": pts
        })

    return {
        "station_id": station_id,
        "hours": hours,
        "total_records": len(records),
        "series": series
    }

@router.get("/logs")
def get_station_logs(
    station_id: int = Query(...),
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(1000, ge=1, le=5000),
    db: Session = Depends(get_db)
):
    cutoff = now_myt_naive() - timedelta(hours=hours)
    query = db.query(TimeseriesData).filter(
        TimeseriesData.station_id == station_id,
        TimeseriesData.timestamp >= cutoff
    )
    records = query.order_by(TimeseriesData.timestamp.desc()).limit(limit * 5).all()

    # Fallback to recent historical logs if no observations in window
    if not records:
        records = db.query(TimeseriesData).filter(
            TimeseriesData.station_id == station_id
        ).order_by(TimeseriesData.timestamp.desc()).limit(limit).all()

    sensors = db.query(Sensor).filter(Sensor.station_id == station_id).all()
    sensor_cols = [{"key": s.metric_key, "name": s.name, "unit": s.unit} for s in sensors]

    rows_by_ts = {}
    for r in records:
        ts_str = r.timestamp.strftime("%Y-%m-%d %H:%M:%S")
        ts_str = to_myt_str(r.timestamp)
        if ts_str not in rows_by_ts:
            rows_by_ts[ts_str] = {"timestamp": ts_str}
        rows_by_ts[ts_str][r.metric_key] = r.value

    # Take up to `limit` rows sorted descending
    sorted_rows = [rows_by_ts[ts] for ts in sorted(rows_by_ts.keys(), reverse=True)[:limit]]

    return {
        "station_id": station_id,
        "total_rows": len(sorted_rows),
        "columns": sensor_cols,
        "rows": sorted_rows
    }

@router.get("/latest")
def get_latest_readings(station_id: int, db: Session = Depends(get_db)):
    sensors = db.query(Sensor).filter(Sensor.station_id == station_id).all()
    results = []
    for s in sensors:
        latest = db.query(TimeseriesData).filter(
            TimeseriesData.station_id == station_id,
            TimeseriesData.metric_key == s.metric_key
        ).order_by(TimeseriesData.timestamp.desc()).first()

        results.append({
            "sensor_id": s.id,
            "name": s.name,
            "metric_key": s.metric_key,
            "unit": s.unit,
            "visualizer_type": s.visualizer_type or "line",
            "value": latest.value if latest else s.current_value,
            "status": s.status,
            "timestamp": to_myt_iso(latest.timestamp) if latest else (to_myt_iso(s.last_reading_time) if s.last_reading_time else None)
        })
    return results

@router.get("/aquarius/query")
def get_aquarius_timeseries(
    station_id: int = Query(...),
    metrics: Optional[str] = Query(None, description="Comma-separated metric keys, e.g. level_avg,rain_tot"),
    hours: Optional[int] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    limit: int = Query(10000, ge=10, le=50000),
    db: Session = Depends(get_db)
):
    station = db.query(Station).filter(Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")

    sensors = db.query(Sensor).filter(Sensor.station_id == station_id).all()
    sensor_map = {
        s.metric_key: {
            "id": s.id,
            "name": s.name,
            "unit": s.unit or "",
            "visualizer_type": s.visualizer_type or "line"
        }
        for s in sensors
    }

    selected_metrics = []
    if metrics:
        selected_metrics = [m.strip() for m in metrics.split(",") if m.strip()]
    else:
        selected_metrics = list(sensor_map.keys())

    query = db.query(TimeseriesData).filter(TimeseriesData.station_id == station_id)
    if selected_metrics:
        query = query.filter(TimeseriesData.metric_key.in_(selected_metrics))

    if start_time:
        try:
            st_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00")).replace(tzinfo=None)
            query = query.filter(TimeseriesData.timestamp >= st_dt)
        except Exception:
            pass
    elif hours:
        cutoff = now_myt_naive() - timedelta(hours=hours)
        query = query.filter(TimeseriesData.timestamp >= cutoff)

    if end_time:
        try:
            et_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00")).replace(tzinfo=None)
            query = query.filter(TimeseriesData.timestamp <= et_dt)
        except Exception:
            pass

    records = query.order_by(TimeseriesData.timestamp.asc()).limit(limit).all()

    if not records:
        fallback_query = db.query(TimeseriesData).filter(TimeseriesData.station_id == station_id)
        if selected_metrics:
            fallback_query = fallback_query.filter(TimeseriesData.metric_key.in_(selected_metrics))
        records = fallback_query.order_by(TimeseriesData.timestamp.desc()).limit(min(limit, 2000)).all()
        records.reverse()

    grouped = {}
    for r in records:
        if r.metric_key not in grouped:
            grouped[r.metric_key] = []
        raw_val = getattr(r, 'raw_value', None)
        is_edited = (raw_val is not None and abs(r.value - raw_val) > 1e-6) or (r.quality_code == "corrected")
        grouped[r.metric_key].append({
            "id": r.id,
            "timestamp": to_myt_iso(r.timestamp),
            "formatted_time": to_myt_str(r.timestamp),
            "value": r.value,
            "raw_value": raw_val if raw_val is not None else r.value,
            "quality_code": r.quality_code or "good",
            "remarks": getattr(r, 'remarks', None),
            "edited_by": getattr(r, 'edited_by', None),
            "edited_at": to_myt_iso(r.edited_at) if getattr(r, 'edited_at', None) else None,
            "is_edited": is_edited
        })

    series = []
    for m_key in selected_metrics:
        pts = grouped.get(m_key, [])
        meta = sensor_map.get(m_key, {"id": 0, "name": m_key, "unit": "", "visualizer_type": "line"})
        vals = [p["value"] for p in pts if p["value"] is not None]
        stat_min = min(vals) if vals else None
        stat_max = max(vals) if vals else None
        stat_avg = (sum(vals) / len(vals)) if vals else None
        latest_val = pts[-1]["value"] if pts else None

        series.append({
            "metric_key": m_key,
            "sensor_id": meta["id"],
            "sensor_name": meta["name"],
            "unit": meta["unit"],
            "visualizer_type": meta["visualizer_type"],
            "points_count": len(pts),
            "latest_value": latest_val,
            "statistics": {
                "min": round(stat_min, 4) if stat_min is not None else None,
                "max": round(stat_max, 4) if stat_max is not None else None,
                "mean": round(stat_avg, 4) if stat_avg is not None else None,
                "count": len(vals)
            },
            "points": pts
        })

    return {
        "station": {
            "id": station.id,
            "name": station.name,
            "code": station.code,
            "site_name": station.site.name if station.site else "",
            "status": station.status
        },
        "available_sensors": [
            {
                "key": s.metric_key,
                "name": s.name,
                "unit": s.unit or "",
                "visualizer_type": s.visualizer_type or "line",
                "current_value": s.current_value
            }
            for s in sensors
        ],
        "total_series": len(series),
        "total_records": len(records),
        "series": series
    }

@router.get("/points/{point_id}")
def get_point_detail(point_id: int, db: Session = Depends(get_db)):
    point = db.query(TimeseriesData).filter(TimeseriesData.id == point_id).first()
    if not point:
        raise HTTPException(status_code=404, detail="Telemetry observation point not found")

    station = db.query(Station).filter(Station.id == point.station_id).first()
    sensor = db.query(Sensor).filter(
        Sensor.station_id == point.station_id,
        Sensor.metric_key == point.metric_key
    ).first()

    raw_val = getattr(point, 'raw_value', None)
    is_edited = (raw_val is not None and abs(point.value - raw_val) > 1e-6) or (point.quality_code == "corrected")

    return {
        "id": point.id,
        "station_id": point.station_id,
        "station_name": station.name if station else f"Station #{point.station_id}",
        "station_code": station.code if station else "",
        "metric_key": point.metric_key,
        "sensor_name": sensor.name if sensor else point.metric_key,
        "unit": sensor.unit if sensor else "",
        "timestamp": to_myt_iso(point.timestamp),
        "formatted_time": to_myt_str(point.timestamp),
        "value": point.value,
        "raw_value": raw_val if raw_val is not None else point.value,
        "quality_code": point.quality_code or "good",
        "remarks": getattr(point, 'remarks', None),
        "edited_by": getattr(point, 'edited_by', None),
        "edited_at": to_myt_iso(point.edited_at) if getattr(point, 'edited_at', None) else None,
        "is_edited": is_edited
    }

@router.patch("/points/{point_id}")
def edit_point_value(point_id: int, payload: PointEditRequest, db: Session = Depends(get_db)):
    point = db.query(TimeseriesData).filter(TimeseriesData.id == point_id).first()
    if not point:
        raise HTTPException(status_code=404, detail="Telemetry observation point not found")

    if getattr(point, 'raw_value', None) is None:
        point.raw_value = point.value

    point.value = payload.value
    point.quality_code = payload.quality_code or "corrected"
    if payload.remarks is not None:
        point.remarks = payload.remarks
    point.edited_by = payload.edited_by or "Hydrologist / Operator"
    point.edited_at = now_myt_naive()

    sensor = db.query(Sensor).filter(
        Sensor.station_id == point.station_id,
        Sensor.metric_key == point.metric_key
    ).first()
    if sensor:
        latest = db.query(TimeseriesData).filter(
            TimeseriesData.station_id == point.station_id,
            TimeseriesData.metric_key == point.metric_key
        ).order_by(TimeseriesData.timestamp.desc()).first()
        if latest and latest.id == point.id:
            sensor.current_value = payload.value

    db.commit()
    db.refresh(point)

    return {
        "status": "success",
        "message": f"Point #{point.id} updated successfully",
        "point": {
            "id": point.id,
            "metric_key": point.metric_key,
            "value": point.value,
            "raw_value": point.raw_value,
            "quality_code": point.quality_code,
            "remarks": point.remarks,
            "edited_by": point.edited_by,
            "edited_at": to_myt_iso(point.edited_at),
            "is_edited": True
        }
    }

@router.post("/points/{point_id}/revert")
def revert_point_value(point_id: int, db: Session = Depends(get_db)):
    point = db.query(TimeseriesData).filter(TimeseriesData.id == point_id).first()
    if not point:
        raise HTTPException(status_code=404, detail="Telemetry observation point not found")

    raw_val = getattr(point, 'raw_value', None)
    if raw_val is None:
        return {"status": "noop", "message": "Point already has its raw initial value", "point_id": point_id}

    point.value = raw_val
    point.quality_code = "good"
    point.remarks = f"Reverted back to raw instrument reading ({raw_val})"
    point.edited_at = now_myt_naive()

    sensor = db.query(Sensor).filter(
        Sensor.station_id == point.station_id,
        Sensor.metric_key == point.metric_key
    ).first()
    if sensor:
        latest = db.query(TimeseriesData).filter(
            TimeseriesData.station_id == point.station_id,
            TimeseriesData.metric_key == point.metric_key
        ).order_by(TimeseriesData.timestamp.desc()).first()
        if latest and latest.id == point.id:
            sensor.current_value = raw_val

    db.commit()
    db.refresh(point)

    return {
        "status": "success",
        "message": f"Point #{point.id} reverted to raw value {raw_val}",
        "point": {
            "id": point.id,
            "metric_key": point.metric_key,
            "value": point.value,
            "raw_value": point.raw_value,
            "quality_code": point.quality_code,
            "remarks": point.remarks,
            "is_edited": False
        }
    }
