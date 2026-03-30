"""NeuroEdge v2 — Gaze Analytics Service"""
from collections import deque, Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

GAZE_ZONES = {
    "NW": (0.0, 0.0, 0.33, 0.33), "N": (0.33, 0.0, 0.67, 0.33), "NE": (0.67, 0.0, 1.0, 0.33),
    "W":  (0.0, 0.33, 0.33, 0.67),"C": (0.33, 0.33, 0.67, 0.67),"E":  (0.67, 0.33, 1.0, 0.67),
    "SW": (0.0, 0.67, 0.33, 1.0), "S": (0.33, 0.67, 0.67, 1.0), "SE": (0.67, 0.67, 1.0, 1.0),
}
ZONE_TO_CMD = {
    "NW": "MOVE_TOPLEFT", "N": "MOVE_FORWARD", "NE": "MOVE_TOPRIGHT",
    "W": "MOVE_LEFT", "E": "MOVE_RIGHT",
    "SW": "SCAN_LEFT", "S": "MOVE_BACKWARD", "SE": "SCAN_RIGHT",
}

def classify_zone(x: float, y: float) -> str:
    for zone, (x1, y1, x2, y2) in GAZE_ZONES.items():
        if x1 <= x < x2 and y1 <= y < y2:
            return zone
    return "C"


@dataclass
class GazeSession:
    session_id: str
    start_time: datetime = field(default_factory=datetime.utcnow)
    blink_count: int = 0
    total_samples: int = 0
    fatigue_buf: deque = field(default_factory=lambda: deque(maxlen=200))
    zone_history: deque = field(default_factory=lambda: deque(maxlen=500))
    ear_buf: deque = field(default_factory=lambda: deque(maxlen=50))
    blink_times: list = field(default_factory=list)


class GazeAnalyticsService:
    def __init__(self):
        self.sessions: dict[str, GazeSession] = {}
        self.fatigue_score: float = 0.0
        self.current_zone: str = "C"
        self.last_robot_cmd: Optional[str] = None

    def _session(self, sid: str) -> GazeSession:
        if sid not in self.sessions:
            self.sessions[sid] = GazeSession(sid)
        return self.sessions[sid]

    def update(self, event) -> Optional[str]:
        sess = self._session(event.session_id)
        sess.total_samples += 1
        zone = classify_zone(event.gaze_x, event.gaze_y)
        sess.zone_history.append(zone)
        self.current_zone = zone

        if event.blink_detected:
            sess.blink_count += 1
            sess.blink_times.append(datetime.utcnow())

        ear = (event.ear_left + event.ear_right) / 2
        sess.ear_buf.append(ear)
        if len(sess.ear_buf) >= 10:
            avg_ear = sum(sess.ear_buf) / len(sess.ear_buf)
            self.fatigue_score = float(max(0.0, min(1.0, (0.32 - avg_ear) / 0.12)))
            sess.fatigue_buf.append(self.fatigue_score)

        # Robot command from dwell (10 consecutive frames in same non-centre zone)
        cmd = None
        if len(sess.zone_history) >= 10:
            recent = list(sess.zone_history)[-10:]
            if all(z == zone for z in recent) and zone != "C":
                cmd = ZONE_TO_CMD.get(zone)
                self.last_robot_cmd = cmd
        return cmd

    def get_session_stats(self, session_id: str) -> dict:
        sess = self._session(session_id)
        duration = (datetime.utcnow() - sess.start_time).total_seconds()
        zone_counts = Counter(sess.zone_history)
        dominant = zone_counts.most_common(1)[0][0] if zone_counts else "C"
        avg_fat = sum(sess.fatigue_buf) / len(sess.fatigue_buf) if sess.fatigue_buf else 0.0
        return {
            "session_id": session_id, "duration_seconds": round(duration, 1),
            "total_blinks": sess.blink_count, "avg_fatigue": round(avg_fat, 3),
            "dominant_zone": dominant, "samples": sess.total_samples,
            "zone_distribution": dict(zone_counts.most_common()),
        }
