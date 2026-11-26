from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.alert import Alert
from app.models.station import Station

router = APIRouter(prefix="/alerts", tags=["Alerts & Events"])

@router.get("")
def get_alerts(
    status: Optional[str] = Query("all"),
    severity: Optional[str] = Query(None),
    station_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    query = db.query(Alert)
    if status and status != "all":
        query = query.filter(Alert.status == status)
    if severity and severity != "all":
        query = query.filter(Alert.severity == severity)
    if station_id:
        query = query.filter(Alert.station_id == station_id)
    
    alerts = query.order_by(Alert.created_at.desc()).limit(limit).all()
    
    result = []
    for a in alerts:
        st = db.query(Station).filter(Station.id == a.station_id).first()
        result.append({
            "id": a.id,
            "station_id": a.station_id,
            "station_name": st.name if st else "Station",
            "station_code": st.code if st else "--",
            "metric_key": a.metric_key,
            "severity": a.severity,
            "message": a.message,
            "triggered_value": a.triggered_value,
            "threshold_value": a.threshold_value,
            "status": a.status,
            "acknowledged_by": a.acknowledged_by,
            "acknowledged_at": a.acknowledged_at,
            "resolved_at": a.resolved_at,
            "created_at": a.created_at
        })
    return result

@router.post("/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int, user_name: Optional[str] = "Operator", db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.status = "acknowledged"
    alert.acknowledged_by = user_name
    alert.acknowledged_at = datetime.utcnow()
    db.commit()
    return {"message": "Alert acknowledged", "status": "acknowledged"}

@router.post("/{alert_id}/resolve")
def resolve_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.status = "resolved"
    alert.resolved_at = datetime.utcnow()
    db.commit()
    return {"message": "Alert resolved", "status": "resolved"}
