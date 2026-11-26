from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from app.database import Base

class ReportJob(Base):
    __tablename__ = "report_jobs"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(150), nullable=False)
    report_type = Column(String(50), default="telemetry_summary") # telemetry_summary, compliance, alert_audit, station_health
    frequency = Column(String(50), default="daily") # daily, weekly, monthly, on_demand
    target_format = Column(String(20), default="csv") # csv, xlsx, pdf
    parameters_json = Column(Text, nullable=True)
    recipients_json = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ReportFile(Base):
    __tablename__ = "report_files"
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, nullable=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(255), nullable=True)
    file_size_bytes = Column(Integer, default=0)
    file_format = Column(String(20), default="csv")
    download_url = Column(String(255), nullable=True)
    status = Column(String(20), default="completed") # processing, completed, failed
    created_at = Column(DateTime, default=datetime.utcnow)
