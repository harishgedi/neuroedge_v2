"""
NeuroEdge v2 — Pytest Conftest
================================
Shared fixtures for all test modules.
Keeps test files clean — no repeated setup code.
"""
import pytest
from backend.services.anomaly_detector import AnomalyDetector
from backend.services.network_reliability import NetworkReliabilityService, SliceSLA
from backend.services.gaze_analytics import GazeAnalyticsService


@pytest.fixture
def detector():
    """Fresh AnomalyDetector with default settings."""
    return AnomalyDetector(window=50, z_threshold=2.5)


@pytest.fixture
def detector_tight():
    """AnomalyDetector with tight thresholds — triggers faster for test speed."""
    return AnomalyDetector(window=10, z_threshold=1.5)


@pytest.fixture
def network_svc():
    """Fresh NetworkReliabilityService."""
    return NetworkReliabilityService()


@pytest.fixture
def gaze_svc():
    """Fresh GazeAnalyticsService."""
    return GazeAnalyticsService()


@pytest.fixture
def urllc_sla():
    """URLLC slice SLA — strictest constraints (≤10ms latency, ≤0.00001 loss)."""
    return SliceSLA(
        slice_type="URLLC",
        max_latency_ms=10.0,
        max_packet_loss=0.00001,
        min_throughput_kbps=1000,
        reliability_target=0.99999,
    )


@pytest.fixture
def embb_sla():
    """eMBB slice SLA — broadband constraints."""
    return SliceSLA(
        slice_type="eMBB",
        max_latency_ms=100.0,
        max_packet_loss=0.005,
        min_throughput_kbps=50000,
        reliability_target=0.9990,
    )


@pytest.fixture
def warmed_detector():
    """AnomalyDetector with 30 baseline samples already fed (10ms latency on node-1)."""
    det = AnomalyDetector(window=50, z_threshold=2.5)
    for _ in range(30):
        det.check_latency("node-1", 10.0, slice_type="eMBB")
    return det
