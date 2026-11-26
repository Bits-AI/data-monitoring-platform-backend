from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.database import Base
from app.time_utils import now_myt_naive

class Site(Base):
    __tablename__ = "sites"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    code = Column(String(50), nullable=True)
    client_name = Column(String(100), default="JPS - WPKL")
    description = Column(Text, nullable=True)
    region = Column(String(100), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=now_myt_naive)

    stations = relationship("Station", back_populates="site", cascade="all, delete-orphan")

class Station(Base):
    __tablename__ = "stations"
    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(Integer, ForeignKey("sites.id"), nullable=False)
    name = Column(String(100), nullable=False)
    code = Column(String(50), nullable=True)
    station_type = Column(String(50), default="Hydrology / Water Level")
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    elevation = Column(Float, default=0.0)
    status = Column(String(20), default="online") # online, warning, offline, maintenance
    battery_level = Column(Float, default=100.0) # percentage / V
    signal_strength = Column(Integer, default=-75) # dBm / RSSI
    solar_charging = Column(Boolean, default=True)
    logger_brand = Column(String(50), default="Neon")
    logger_type = Column(String(50), default="Neon REST")
    serial_number = Column(String(100), nullable=True)
    last_seen = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=now_myt_naive)
    created_at = Column(DateTime, default=now_myt_naive)

    site = relationship("Site", back_populates="stations")
    loggers = relationship("Logger", back_populates="station", cascade="all, delete-orphan")
    sensors = relationship("Sensor", back_populates="station", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="station", cascade="all, delete-orphan")

class Logger(Base):
    __tablename__ = "loggers"
    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=False)
    model = Column(String(100), nullable=False)
    serial_number = Column(String(100), unique=True, nullable=False)
    firmware_version = Column(String(50), nullable=True)
    ip_address = Column(String(50), nullable=True)
    connection_type = Column(String(50), default="Cellular 4G/LTE")
    status = Column(String(20), default="active")
    last_heartbeat = Column(DateTime, default=datetime.utcnow)
    last_heartbeat = Column(DateTime, default=now_myt_naive)

    station = relationship("Station", back_populates="loggers")

class Sensor(Base):
    __tablename__ = "sensors"
    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(Integer, ForeignKey("stations.id"), nullable=False)
    name = Column(String(100), nullable=False)
    metric_key = Column(String(50), index=True, nullable=False)
    unit = Column(String(20), nullable=False)
    sensor_type = Column(String(50), nullable=True)
    visualizer_type = Column(String(30), default="line") # line, bar, ph_scale, battery, compass
    parameter_code = Column(String(50), nullable=True)
    current_value = Column(Float, nullable=True)
    min_limit = Column(Float, nullable=True)
    max_limit = Column(Float, nullable=True)
    status = Column(String(20), default="normal") # normal, warning, critical
    last_reading_time = Column(DateTime, default=datetime.utcnow)
    last_reading_time = Column(DateTime, default=now_myt_naive)

    station = relationship("Station", back_populates="sensors")
