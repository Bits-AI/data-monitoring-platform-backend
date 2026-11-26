from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base

class ThresholdRule(Base):
    __tablename__ = "threshold_rules"
    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=True) # Null means applies to all
    metric_key = Column(String(50), nullable=False)
    rule_name = Column(String(100), nullable=False)
    comparison_operator = Column(String(10), nullable=False) # >, <, >=, <=, ==
    warning_value = Column(Float, nullable=False)
    critical_value = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=False)
    rule_id = Column(Integer, ForeignKey("threshold_rules.id"), nullable=True)
    metric_key = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False) # info, warning, critical
    message = Column(Text, nullable=False)
    triggered_value = Column(Float, nullable=False)
    threshold_value = Column(Float, nullable=False)
    status = Column(String(20), default="active") # active, acknowledged, resolved
    acknowledged_by = Column(String(100), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    station = relationship("Station", back_populates="alerts")

class NotificationChannel(Base):
    __tablename__ = "notification_channels"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    channel_type = Column(String(50), nullable=False) # email, webhook, sms, slack
    target = Column(String(255), nullable=False) # email address or webhook URL
    is_active = Column(Boolean, default=True)

class NotificationDispatch(Base):
    __tablename__ = "notification_dispatches"
    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)
    channel_id = Column(Integer, ForeignKey("notification_channels.id"), nullable=False)
    status = Column(String(20), default="sent") # pending, sent, failed
    dispatched_at = Column(DateTime, default=datetime.utcnow)
    response_details = Column(Text, nullable=True)
