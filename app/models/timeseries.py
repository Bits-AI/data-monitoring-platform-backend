from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index
from app.database import Base

class TimeseriesData(Base):
    __tablename__ = "timeseries_data"
    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=False, index=True)
    sensor_id = Column(Integer, ForeignKey("sensors.id"), nullable=True, index=True)
    metric_key = Column(String(50), nullable=False, index=True)
    value = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    quality_code = Column(String(20), default="good")
    raw_value = Column(Float, nullable=True)
    remarks = Column(String(255), nullable=True)
    edited_by = Column(String(100), nullable=True)
    edited_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_station_metric_time", "station_id", "metric_key", "timestamp"),
    )
