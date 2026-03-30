"""NeuroEdge v2 — Settings"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "NeuroEdge"
    app_version: str = "2.0.0"
    app_env: str = "development"
    debug: bool = True
    secret_key: str = "change-me"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: list[str] = ["http://localhost:5173"]
    database_url: str = "sqlite+aiosqlite:///./neuroedge.db"
    camera_index: int = 0
    gaze_ear_threshold: float = 0.22
    fatigue_blink_rate: int = 25
    iot_node_count: int = 8
    reliability_target: float = 0.9995
    lora_range_km: float = 15.0
    anomaly_window: int = 50
    anomaly_threshold: float = 2.5
    ppg_sample_rate_hz: int = 100

@lru_cache
def get_settings() -> Settings:
    return Settings()
