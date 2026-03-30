"""NeuroEdge v2 — Network Reliability Service with SLA enforcement"""
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


SLICE_SLAS_CONFIG = {
    "URLLC": {"latency": 10.0,   "loss": 0.00001, "target": 0.99999},
    "eMBB":  {"latency": 100.0,  "loss": 0.005,   "target": 0.9990},
    "mMTC":  {"latency": 1000.0, "loss": 0.02,    "target": 0.9950},
    "eMBB3G":{"latency": 200.0,  "loss": 0.08,    "target": 0.9800},
}


@dataclass
class SliceSLA:
    slice_type: str
    max_latency_ms: float
    max_packet_loss: float
    min_throughput_kbps: float
    reliability_target: float
    breach_count: int = 0
    total_checks: int = 0

    @property
    def sla_breach_rate(self) -> float:
        return self.breach_count / self.total_checks if self.total_checks else 0.0

    def check(self, latency_ms: float, packet_loss: float,
              throughput_kbps: float = 999999.0) -> tuple[bool, list[str]]:
        self.total_checks += 1
        violations = []
        if latency_ms > self.max_latency_ms:
            violations.append(f"latency {latency_ms:.1f}ms > {self.max_latency_ms}ms")
        if packet_loss > self.max_packet_loss:
            violations.append(f"loss {packet_loss:.6f} > {self.max_packet_loss}")
        if violations:
            self.breach_count += 1
        return not bool(violations), violations


@dataclass
class NodeState:
    node_id: str
    network_gen: str = "5G"
    slice_type: str = "eMBB"
    distance_km: float = 1.0
    lat_buf: deque = field(default_factory=lambda: deque(maxlen=100))
    loss_buf: deque = field(default_factory=lambda: deque(maxlen=100))
    rel_buf: deque = field(default_factory=lambda: deque(maxlen=100))
    packet_count: int = 0
    lost_count: int = 0
    last_seen: Optional[datetime] = None


class NetworkReliabilityService:
    def __init__(self):
        self.nodes: dict[str, NodeState] = {}
        self.current_reliability: float = 1.0
        self._start: float = time.time()
        self._total_packets: int = 0
        self._total_lost: int = 0

    def _node(self, node_id: str, gen: str, slc: str, dist: float) -> NodeState:
        if node_id not in self.nodes:
            self.nodes[node_id] = NodeState(node_id, gen, slc, dist)
        return self.nodes[node_id]

    def _avg(self, d: deque) -> float:
        return sum(d) / len(d) if d else 0.0

    def update(self, node_id: str, latency_ms: float, packet_loss: float,
               reliability: float, net_gen: str = "5G", slice_type: str = "eMBB",
               distance_km: float = 1.0):
        n = self._node(node_id, net_gen, slice_type, distance_km)
        n.lat_buf.append(latency_ms)
        n.loss_buf.append(packet_loss)
        n.rel_buf.append(reliability)
        n.packet_count += 1
        n.last_seen = datetime.utcnow()
        n.network_gen = net_gen
        n.slice_type = slice_type
        self._total_packets += 1
        if packet_loss > 0.5:
            self._total_lost += 1
        if self._total_packets > 0:
            self.current_reliability = 1.0 - (self._total_lost / self._total_packets)

    def get_node_stats(self, node_id: str) -> Optional[dict]:
        n = self.nodes.get(node_id)
        if not n:
            return None
        cfg = SLICE_SLAS_CONFIG.get(n.slice_type, SLICE_SLAS_CONFIG["eMBB"])
        rel = self._avg(n.rel_buf)
        return {
            "node_id": node_id,
            "network_gen": n.network_gen,
            "slice_type": n.slice_type,
            "distance_km": n.distance_km,
            "avg_latency_ms": round(self._avg(n.lat_buf), 2),
            "avg_packet_loss": round(self._avg(n.loss_buf), 6),
            "avg_reliability": round(rel, 6),
            "sla_met": rel >= cfg["target"],
            "sla_target": cfg["target"],
            "packet_count": n.packet_count,
            "last_seen": n.last_seen.isoformat() if n.last_seen else None,
        }

    def get_all_stats(self) -> list[dict]:
        return [s for nid in self.nodes if (s := self.get_node_stats(nid))]

    def get_network_summary(self) -> dict:
        all_s = self.get_all_stats()
        return {
            "total_nodes": len(self.nodes),
            "nodes_sla_met": sum(1 for s in all_s if s["sla_met"]),
            "global_reliability": round(self.current_reliability, 6),
            "uptime_seconds": int(time.time() - self._start),
            "total_packets": self._total_packets,
            "total_lost": self._total_lost,
        }
