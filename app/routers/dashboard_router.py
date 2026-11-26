from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.station import Station, Site, Sensor
from app.models.alert import Alert

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/summary")
def get_dashboard_summary(db: Session = Depends(get_db)):
    total_stations = db.query(Station).count()
    online_stations = db.query(Station).filter(Station.status == "online").count()
    warning_stations = db.query(Station).filter(Station.status == "warning").count()
    offline_stations = db.query(Station).filter(Station.status.in_(["offline", "maintenance"])).count()
    
    total_sites = db.query(Site).count()
    total_sensors = db.query(Sensor).count()
    active_alerts = db.query(Alert).filter(Alert.status == "active").count()

    # System Health metric %
    health_pct = round(((online_stations + (warning_stations * 0.7)) / max(1, total_stations)) * 100, 1)

    return {
        "total_stations": total_stations,
        "online_stations": online_stations,
        "warning_stations": warning_stations,
        "offline_stations": offline_stations,
        "total_sites": total_sites,
        "total_sensors": total_sensors,
        "active_alerts": active_alerts,
        "system_health_percent": health_pct
    }

@router.get("/sites")
def get_sites_summary(db: Session = Depends(get_db)):
    sites = db.query(Site).all()
    result = []
    for site in sites:
        stations = db.query(Station).filter(Station.site_id == site.id).all()
        online_count = sum(1 for s in stations if s.status == "online")
        warning_count = sum(1 for s in stations if s.status == "warning")
        offline_count = sum(1 for s in stations if s.status in ["offline", "maintenance"])
        
        result.append({
            "id": site.id,
            "name": site.name,
            "code": site.code,
            "client_name": site.client_name,
            "region": site.region,
            "description": site.description,
            "latitude": site.latitude,
            "longitude": site.longitude,
            "total_stations": len(stations),
            "online_stations": online_count,
            "warning_stations": warning_count,
            "offline_stations": offline_count,
            "status": "warning" if warning_count > 0 else ("offline" if (len(stations) > 0 and online_count == 0) else "healthy"),
            "stations": [
                {
                    "id": st.id,
                    "name": st.name,
                    "code": st.code,
                    "logger_brand": st.logger_brand,
                    "logger_type": st.logger_type,
                    "status": st.status,
                    "battery": st.battery_level,
                    "signal": st.signal_strength,
                    "last_seen": st.last_seen
                }
                for st in stations
            ]
        })
    return result
