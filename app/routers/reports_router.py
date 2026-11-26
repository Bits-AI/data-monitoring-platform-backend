import io
import csv
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Response, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.report import ReportJob, ReportFile
from app.models.timeseries import TimeseriesData
from app.models.station import Station
from app.time_utils import now_myt_naive, to_myt_str

router = APIRouter(prefix="/reports", tags=["Reports & Exports"])

@router.get("/jobs")
def list_report_jobs(db: Session = Depends(get_db)):
    jobs = db.query(ReportJob).all()
    return [
        {
            "id": j.id,
            "title": j.title,
            "report_type": j.report_type,
            "format": j.format,
            "schedule": j.schedule,
            "is_active": j.is_active,
            "last_run": j.last_run
        }
        for j in jobs
    ]

@router.get("/files")
def list_generated_reports(limit: int = 50, db: Session = Depends(get_db)):
    files = db.query(ReportFile).order_by(ReportFile.created_at.desc()).limit(limit).all()
    return [
        {
            "id": f.id,
            "filename": f.filename,
            "file_size_bytes": f.file_size_bytes,
            "format": f.format,
            "created_at": f.created_at
        }
        for f in files
    ]

@router.get("/export/csv")
def export_raw_csv(
    station_id: Optional[int] = None,
    metric_key: Optional[str] = None,
    hours: Optional[int] = 48,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(TimeseriesData)

    if start_time:
        try:
            start_dt = datetime.fromisoformat(start_time.replace("Z", ""))
            query = query.filter(TimeseriesData.timestamp >= start_dt)
        except Exception:
            pass
    elif hours:
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        cutoff = now_myt_naive() - timedelta(hours=hours)
        query = query.filter(TimeseriesData.timestamp >= cutoff)

    if end_time:
        try:
            end_dt = datetime.fromisoformat(end_time.replace("Z", ""))
            query = query.filter(TimeseriesData.timestamp <= end_dt)
        except Exception:
            pass

    if station_id:
        query = query.filter(TimeseriesData.station_id == station_id)
    if metric_key:
        query = query.filter(TimeseriesData.metric_key == metric_key)
    
    records = query.order_by(TimeseriesData.timestamp.asc()).all()
    stations = {s.id: s for s in db.query(Station).all()}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp_UTC", "Station_Code", "Station_Name", "Metric_Key", "Value", "Quality_Code"])

    for r in records:
        st = stations.get(r.station_id)
        writer.writerow([
            r.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            st.code if st else "",
            st.name if st else "",
            r.metric_key,
            r.value,
            r.quality_code
        ])

    filename = f"telemetry_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    filename = f"telemetry_export_{now_myt_naive().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
