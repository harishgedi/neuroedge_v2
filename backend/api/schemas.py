"""NeuroEdge v2 — API Schemas"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class GazeEventIn(BaseModel):
    session_id: str
    gaze_x: float = Field(..., ge=0, le=1)
    gaze_y: float = Field(..., ge=0, le=1)
    gaze_zone: str = "C"
    blink_detected: bool = False
    blink_duration_ms: float = 0.0
    ear_left: float = 0.0
    ear_right: float = 0.0
    fatigue_score: float = 0.0
    head_yaw: float = 0.0
    head_pitch: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class NetworkTelemetryIn(BaseModel):
    node_id: str
    latency_ms: float = Field(..., ge=0)
    packet_loss: float = Field(..., ge=0, le=1)
    rssi_dbm: float
    snr_db: float
    throughput_kbps: float = Field(..., ge=0)
    reliability: float = Field(..., ge=0, le=1)
    network_gen: str = "5G"
    slice_type: str = "eMBB"
    distance_km: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class BiometricSampleIn(BaseModel):
    node_id: str
    bpm: float = Field(..., ge=20, le=220)
    spo2: float = Field(..., ge=50, le=100)
    ppg_amplitude: float
    stress_index: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class RobotCommandIn(BaseModel):
    robot_id: str
    command: str
    source: str = "API"
    gaze_zone: Optional[str] = None
    target_x: float = 0.0
    target_y: float = 0.0

class AlertIn(BaseModel):
    alert_type: str
    severity: str = "WARN"
    source: str
    message: str

class SystemStatusOut(BaseModel):
    status: str
    ws_connections: int
    gaze_events_total: int
    network_samples_total: int
    robot_commands_total: int
    biometric_samples_total: int
    open_alerts: int
    network_reliability: float
    fatigue_score: float
    anomaly_score: float
    avg_bpm: float
    uptime_seconds: int
