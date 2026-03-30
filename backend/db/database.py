"""NeuroEdge v2 — Database models"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Float, Integer, Boolean, DateTime, Text, func
from datetime import datetime
from typing import AsyncGenerator, Optional
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from backend.config import get_settings

settings = get_settings()
engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

class GazeEvent(Base):
    __tablename__ = "gaze_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    gaze_x: Mapped[float] = mapped_column(Float)
    gaze_y: Mapped[float] = mapped_column(Float)
    gaze_zone: Mapped[str] = mapped_column(String(4))
    blink_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    blink_duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    ear_left: Mapped[float] = mapped_column(Float, default=0.0)
    ear_right: Mapped[float] = mapped_column(Float, default=0.0)
    fatigue_score: Mapped[float] = mapped_column(Float, default=0.0)
    head_yaw: Mapped[float] = mapped_column(Float, default=0.0)
    head_pitch: Mapped[float] = mapped_column(Float, default=0.0)

class NetworkTelemetry(Base):
    __tablename__ = "network_telemetry"
    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[str] = mapped_column(String(32), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    latency_ms: Mapped[float] = mapped_column(Float)
    packet_loss: Mapped[float] = mapped_column(Float)
    rssi_dbm: Mapped[float] = mapped_column(Float)
    snr_db: Mapped[float] = mapped_column(Float)
    throughput_kbps: Mapped[float] = mapped_column(Float)
    reliability: Mapped[float] = mapped_column(Float)
    network_gen: Mapped[str] = mapped_column(String(4))
    slice_type: Mapped[str] = mapped_column(String(8))
    distance_km: Mapped[float] = mapped_column(Float, default=0.0)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    anomaly_score: Mapped[float] = mapped_column(Float, default=0.0)

class RobotCommand(Base):
    __tablename__ = "robot_commands"
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    robot_id: Mapped[str] = mapped_column(String(32))
    command: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(16))
    gaze_zone: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    target_x: Mapped[float] = mapped_column(Float, default=0.0)
    target_y: Mapped[float] = mapped_column(Float, default=0.0)
    executed: Mapped[bool] = mapped_column(Boolean, default=False)

class BiometricSample(Base):
    __tablename__ = "biometric_samples"
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    node_id: Mapped[str] = mapped_column(String(32))
    bpm: Mapped[float] = mapped_column(Float)
    spo2: Mapped[float] = mapped_column(Float, default=98.0)
    ppg_amplitude: Mapped[float] = mapped_column(Float)
    stress_index: Mapped[float] = mapped_column(Float, default=0.0)
    is_alert: Mapped[bool] = mapped_column(Boolean, default=False)

class AlertEvent(Base):
    __tablename__ = "alert_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    alert_type: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(8))
    source: Mapped[str] = mapped_column(String(32))
    message: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
