"""
NeuroEdge v2 — FastAPI Application
====================================
v1 WEAKNESS (Mary Giblin would spot):
  - /health returned just {"status":"ok"} — no component checks
  - No /readyz separate from /healthz (K8s needs both)
  - No VNF status endpoint (Dr. Fallon needs this)
  - No SLA summary endpoint
  - WebSocket had no auth / client-id validation

v2 FIX:
  - /healthz = liveness (is process alive?)
  - /readyz  = readiness (is DB + dependencies ready?)
  - /api/vnf = VNF fleet status (Dr. Fallon)
  - /api/sla = per-slice SLA summary (Dr. Fallon)
  - /api/heal= healing log (CAMINO alignment)
  - WebSocket sends structured typed messages
"""
import asyncio, json, time, uuid, os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import get_settings
from backend.db.database import (init_db, get_db, GazeEvent, NetworkTelemetry,
                                  RobotCommand, BiometricSample, AlertEvent)
from backend.api.schemas import (GazeEventIn, NetworkTelemetryIn, BiometricSampleIn,
                                 RobotCommandIn, AlertIn, SystemStatusOut)
from backend.services.anomaly_detector import AnomalyDetector
from backend.services.network_reliability import NetworkReliabilityService
from backend.services.gaze_analytics import GazeAnalyticsService

settings = get_settings()
_start = time.time()


# ── WebSocket Manager ────────────────────────────────────────────────────
class WSManager:
    def __init__(self):
        self.clients: dict[str, WebSocket] = {}

    async def connect(self, ws: WebSocket, cid: str):
        await ws.accept()
        self.clients[cid] = ws
        # Send welcome state snapshot
        await ws.send_text(json.dumps({"type": "CONNECTED", "client_id": cid,
                                        "ts": datetime.now(timezone.utc).isoformat()}))

    def disconnect(self, cid: str):
        self.clients.pop(cid, None)

    async def broadcast(self, msg: dict):
        dead = []
        payload = json.dumps(msg, default=str)
        for cid, ws in self.clients.items():
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(cid)
        for cid in dead:
            self.disconnect(cid)


ws_mgr  = WSManager()
anomaly = AnomalyDetector()
net_svc = NetworkReliabilityService()
gaze_svc= GazeAnalyticsService()

# VNF fleet state shared with simulator (in-process simulation)
_vnf_states: dict[str, dict] = {}
_sla_summary: dict[str, dict] = {}
_edge_nodes: dict[str, dict]  = {}  # Mobile/Android remote sensors

# Lite Architecture (Android Ngrok Tunneled Telemetry)
_latest_lite_metrics = {
    "heart_rate": "N/A",
    "spo2": "N/A",
    "wifi_strength": "N/A",
    "battery_level": "N/A",
    "last_update": "Waiting for signal..."
}


# ── Lifespan ─────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    asyncio.create_task(_heartbeat())
    yield

app = FastAPI(
    title="NeuroEdge API v2",
    description="Edge AI + 5G + VNF + Cloud-Native Research Platform",
    version="2.0.0",
    lifespan=lifespan
)
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


async def _heartbeat():
    while True:
        await asyncio.sleep(2)
        await ws_mgr.broadcast({
            "type": "HEARTBEAT",
            "payload": {
                "ts": datetime.now(timezone.utc).isoformat(),
                "reliability": round(net_svc.current_reliability, 6),
                "fatigue": round(gaze_svc.fatigue_score, 3),
                "anomaly_score": round(anomaly.last_score, 3),
                "anomaly_votes_last": getattr(anomaly, "_last_votes", 0),
                "ws_clients": len(ws_mgr.clients),
                "uptime_s": int(time.time() - _start),
            }
        })


# ── WebSocket ─────────────────────────────────────────────────────────────
@app.websocket("/ws/{client_id}")
async def ws_endpoint(ws: WebSocket, client_id: str):
    await ws_mgr.connect(ws, client_id)
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            mtype = msg.get("type")
            
            if mtype == "PING":
                await ws.send_text(json.dumps({"type": "PONG", "ts": datetime.utcnow().isoformat()}))
            
            elif mtype == "EDGE_TELEMETRY":
                # Received from mobile/android client
                payload = msg.get("payload", {})
                nid = payload.get("node_id", "unknown-mobile")
                _edge_nodes[nid] = {**payload, "last_seen": time.time()}
                # Broadcast to main dashboard
                await ws_mgr.broadcast({"type": "EDGE_UPDATE", "payload": payload})
    except WebSocketDisconnect:
        ws_mgr.disconnect(client_id)


# ── Liveness & Readiness (K8s probes) ────────────────────────────────────
@app.get("/healthz", tags=["Observability"], summary="Liveness probe")
async def liveness():
    """K8s liveness: is the process running?"""
    return {"status": "alive", "uptime_s": int(time.time() - _start)}


@app.get("/readyz", tags=["Observability"], summary="Readiness probe")
async def readiness(db: AsyncSession = Depends(get_db)):
    """
    K8s readiness: are all dependencies ready?
    Mary Giblin's programme emphasises this distinction.
    """
    checks = {}
    # DB check
    try:
        await db.scalar(select(func.count()).select_from(AlertEvent))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # Anomaly detector check
    checks["anomaly_detector"] = "ok" if anomaly else "not_initialised"
    checks["gaze_service"]     = "ok" if gaze_svc else "not_initialised"

    all_ok = all(v == "ok" for v in checks.values())
    return {"status": "ready" if all_ok else "not_ready",
            "checks": checks, "ts": datetime.utcnow().isoformat()}


# ── Metrics (Prometheus) ──────────────────────────────────────────────────
@app.get("/metrics", response_class=PlainTextResponse, tags=["Observability"])
async def prometheus_metrics():
    """
    Prometheus scrape endpoint.
    Custom metric: neuroedge_anomaly_score — used by KEDA ScaledObject
    to trigger K8s HPA on network anomaly (v1 had CPU-only HPA).
    """
    lines = [
        "# HELP neuroedge_ws_connections Active WebSocket connections",
        "# TYPE neuroedge_ws_connections gauge",
        f"neuroedge_ws_connections {len(ws_mgr.clients)}",

        "# HELP neuroedge_network_reliability Global 5G network reliability 0-1",
        "# TYPE neuroedge_network_reliability gauge",
        f"neuroedge_network_reliability {net_svc.current_reliability:.6f}",

        "# HELP neuroedge_anomaly_score Composite anomaly score (CUSUM+EWMA+Zscore)",
        "# TYPE neuroedge_anomaly_score gauge",
        f"neuroedge_anomaly_score {anomaly.last_score:.4f}",

        "# HELP neuroedge_anomaly_total Total anomalies detected across all nodes",
        "# TYPE neuroedge_anomaly_total counter",
        f"neuroedge_anomaly_total {anomaly.anomaly_count}",

        "# HELP neuroedge_fatigue_score Operator fatigue 0.0-1.0",
        "# TYPE neuroedge_fatigue_score gauge",
        f"neuroedge_fatigue_score {gaze_svc.fatigue_score:.4f}",

        "# HELP neuroedge_uptime_seconds Process uptime in seconds",
        "# TYPE neuroedge_uptime_seconds counter",
        f"neuroedge_uptime_seconds {int(time.time() - _start)}",
    ]
    # Per-node reliability
    for stats in net_svc.get_all_stats():
        if stats:
            nid = stats["node_id"].replace("-", "_")
            lines += [
                f'neuroedge_node_reliability{{node="{stats["node_id"]}",gen="{stats["network_gen"]}",slice="{stats["slice_type"]}"}} {stats["avg_reliability"]:.6f}',
                f'neuroedge_node_latency_ms{{node="{stats["node_id"]}"}} {stats["avg_latency_ms"]:.2f}',
            ]
    return "\n".join(lines)


# ── System Status ─────────────────────────────────────────────────────────
@app.get("/api/status", response_model=SystemStatusOut, tags=["System"])
async def system_status(db: AsyncSession = Depends(get_db)):
    counts = {}
    for name, model in [("gaze", GazeEvent), ("net", NetworkTelemetry),
                         ("robot", RobotCommand), ("bio", BiometricSample)]:
        counts[name] = await db.scalar(select(func.count()).select_from(model)) or 0
    alerts = await db.scalar(
        select(func.count()).select_from(AlertEvent).where(AlertEvent.resolved == False)) or 0
    avg_bpm = await db.scalar(select(func.avg(BiometricSample.bpm))) or 72.0
    return SystemStatusOut(
        status="operational", ws_connections=len(ws_mgr.clients),
        gaze_events_total=counts["gaze"], network_samples_total=counts["net"],
        robot_commands_total=counts["robot"], biometric_samples_total=counts["bio"],
        open_alerts=alerts, network_reliability=net_svc.current_reliability,
        fatigue_score=gaze_svc.fatigue_score, anomaly_score=anomaly.last_score,
        avg_bpm=round(float(avg_bpm), 1), uptime_seconds=int(time.time() - _start)
    )


# ── VNF Status (Dr. Fallon's NFV research) ───────────────────────────────
@app.get("/api/vnf", tags=["NFV"])
async def vnf_status():
    """VNF fleet state — aligns with Dr. Fallon's ETSI NFV lifecycle research"""
    return {
        "vnf_fleet": _vnf_states,
        "total_vnfs": len(_vnf_states),
        "active": sum(1 for v in _vnf_states.values() if v.get("state") == "ACTIVE"),
        "healing": sum(1 for v in _vnf_states.values() if v.get("state") == "HEALING"),
        "failed": sum(1 for v in _vnf_states.values() if v.get("state") == "FAILED"),
    }

@app.post("/api/vnf/{vnf_id}/heal", tags=["NFV"])
async def trigger_vnf_heal(vnf_id: str):
    """Manual VNF heal trigger — CAMINO intent-driven healing"""
    if vnf_id not in _vnf_states:
        raise HTTPException(404, f"VNF {vnf_id} not found")
    _vnf_states[vnf_id]["state"] = "HEALING"
    await ws_mgr.broadcast({"type": "VNF_HEALING", "payload": {"vnf_id": vnf_id}})
    return {"status": "heal_triggered", "vnf_id": vnf_id}

@app.get("/api/vnf/heal-log", tags=["NFV"])
async def vnf_heal_log():
    """Self-healing event log — maps to CAMINO orchestration decisions"""
    return {"heal_log": anomaly.get_heal_log(50)}


# ── SLA Monitoring (Dr. Fallon) ───────────────────────────────────────────
@app.get("/api/sla", tags=["5G Network"])
async def sla_summary():
    """Per-slice SLA metrics — URLLC/eMBB/mMTC breach rates"""
    return _sla_summary or {"message": "SLA data populates after first telemetry cycle"}

@app.get("/api/edge/nodes", tags=["System"])
async def edge_nodes():
    """Returns active remote mobile devices acting as Edge nodes"""
    # Clean stale nodes (> 30s)
    now = time.time()
    stale = [k for k, v in _edge_nodes.items() if now - v["last_seen"] > 30]
    for k in stale: _edge_nodes.pop(k)
    return _edge_nodes

# ── LITE / TERMUX TELEMETRY WEBHOOKS ──────────────────────────────────────
@app.post("/api/telemetry", tags=["System"])
async def receive_lite_telemetry(request: Request):
    """Endpoint for Android Device to push data over long distance via Ngrok"""
    data = await request.json()
    global _latest_lite_metrics
    _latest_lite_metrics.update(data)
    _latest_lite_metrics["last_update"] = datetime.now().strftime("%H:%M:%S")
    return {"status": "received"}

@app.get("/api/metrics", tags=["System"])
async def get_lite_metrics():
    """Endpoint for the standalone Health Dashboard to fetch live data"""
    return _latest_lite_metrics

# ── REMOTE CONTROL / GAZE BRIDGE ──────────────────────────────────────────
@app.post("/api/gaze/remote", tags=["Eye-Writer"])
async def receive_remote_gaze(payload: dict):
    """
    Broadcasts gaze (x, y) from Mobile Node to Desktop Dashboards.
    This enables 'Phone-as-a-Mouse' remote control.
    """
    await ws_mgr.broadcast({
        "type": "REMOTE_GAZE_UPDATE",
        "payload": {
            "x": payload.get("x"),
            "y": payload.get("y"),
            "ts": datetime.now(timezone.utc).isoformat()
        }
    })
    return {"status": "broadcasted"}

@app.post("/api/sla/update", include_in_schema=False)
async def update_sla(payload: dict):
    """Internal: simulator posts SLA state here"""
    _sla_summary.update(payload)
    return {"ok": True}


# ── Gaze / Eye-Writer ─────────────────────────────────────────────────────
@app.post("/api/gaze", status_code=201, tags=["Eye-Writer"])
async def ingest_gaze(event: GazeEventIn, db: AsyncSession = Depends(get_db)):
    db.add(GazeEvent(**event.model_dump()))
    robot_cmd = gaze_svc.update(event)
    fat_res   = anomaly.check_fatigue(event.fatigue_score)

    if fat_res.is_anomaly:
        db.add(AlertEvent(alert_type="FATIGUE", severity="WARN", source="eye_tracker",
                          message=f"Fatigue {event.fatigue_score:.2f} — action: {fat_res.heal_action}"))

    await ws_mgr.broadcast({"type": "GAZE_UPDATE", "payload": {
        "x": event.gaze_x, "y": event.gaze_y, "zone": event.gaze_zone,
        "blink": event.blink_detected, "fatigue": gaze_svc.fatigue_score,
        "ear": (event.ear_left + event.ear_right) / 2,
        "robot_cmd": robot_cmd, "ts": event.timestamp.isoformat()
    }})
    if robot_cmd:
        db.add(RobotCommand(robot_id="robot-01", command=robot_cmd,
                            source="GAZE", gaze_zone=event.gaze_zone))
        await ws_mgr.broadcast({"type": "ROBOT_CMD", "payload": {
            "robot_id": "robot-01", "command": robot_cmd,
            "source": "GAZE", "zone": event.gaze_zone
        }})
    return {"status": "ok", "robot_cmd": robot_cmd,
            "fatigue_anomaly": fat_res.is_anomaly, "algo_votes": fat_res.algorithm_votes}


@app.get("/api/gaze/recent", tags=["Eye-Writer"])
async def gaze_recent(limit: int = Query(50, le=200), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(GazeEvent).order_by(desc(GazeEvent.id)).limit(limit))
    return [{"id": e.id, "x": e.gaze_x, "y": e.gaze_y, "zone": e.gaze_zone,
             "fatigue": e.fatigue_score, "ts": e.timestamp.isoformat()} for e in rows.scalars()]

@app.get("/api/gaze/session/{session_id}", tags=["Eye-Writer"])
async def gaze_session(session_id: str):
    return gaze_svc.get_session_stats(session_id)


# ── Network Telemetry ─────────────────────────────────────────────────────
@app.post("/api/network", status_code=201, tags=["5G Network"])
async def ingest_network(t: NetworkTelemetryIn, db: AsyncSession = Depends(get_db)):
    lat_res  = anomaly.check_latency(t.node_id, t.latency_ms, t.slice_type)
    loss_res = anomaly.check_packet_loss(t.node_id, t.packet_loss, t.slice_type)
    rssi_res = anomaly.check_rssi(t.node_id, t.rssi_dbm, t.slice_type)
    is_anom  = lat_res.is_anomaly or loss_res.is_anomaly or rssi_res.is_anomaly
    max_votes= max(lat_res.algorithm_votes, loss_res.algorithm_votes, rssi_res.algorithm_votes)
    heal_act = lat_res.heal_action or loss_res.heal_action

    net_svc.update(t.node_id, t.latency_ms, t.packet_loss, t.reliability,
                   t.network_gen, t.slice_type, t.distance_km)

    db.add(NetworkTelemetry(**t.model_dump(), is_anomaly=is_anom,
                             anomaly_score=lat_res.score))
    if is_anom:
        sev = "CRITICAL" if t.slice_type == "URLLC" else "WARN"
        db.add(AlertEvent(alert_type="NET_ANOMALY", severity=sev, source=t.node_id,
                          message=f"{t.node_id}: lat={t.latency_ms:.1f}ms loss={t.packet_loss:.4f} votes={max_votes} → {heal_act}"))

    await ws_mgr.broadcast({"type": "NETWORK_UPDATE", "payload": {
        "node_id": t.node_id, "latency_ms": t.latency_ms,
        "packet_loss": t.packet_loss, "rssi_dbm": t.rssi_dbm,
        "reliability": t.reliability, "is_anomaly": is_anom,
        "network_gen": t.network_gen, "slice_type": t.slice_type,
        "algo_votes": max_votes, "heal_action": heal_act,
        "ts": t.timestamp.isoformat()
    }})
    return {"status": "ok", "anomaly": is_anom,
            "algo_votes": max_votes, "heal_action": heal_act}

@app.get("/api/network/nodes", tags=["5G Network"])
async def network_nodes():
    return net_svc.get_all_stats()

@app.get("/api/network/summary", tags=["5G Network"])
async def network_summary():
    return net_svc.get_network_summary()

@app.get("/api/network/anomaly-report", tags=["5G Network"])
async def anomaly_report():
    """Full anomaly report with CUSUM/EWMA/Z-score breakdown"""
    return {"heal_log": anomaly.get_heal_log(30),
            "anomaly_count": anomaly.anomaly_count,
            "last_composite_score": anomaly.last_score,
            "algorithms": ["CUSUM", "EWMA", "Z-score"],
            "voting_policy": "2-of-3 majority"}


# ── Biometrics ────────────────────────────────────────────────────────────
@app.post("/api/biometrics", status_code=201, tags=["Biometrics"])
async def ingest_bio(b: BiometricSampleIn, db: AsyncSession = Depends(get_db)):
    bpm_res  = anomaly.check_bpm(b.bpm)
    is_alert = bpm_res.is_anomaly or b.bpm < 45 or b.bpm > 130
    db.add(BiometricSample(**b.model_dump(), is_alert=is_alert))
    if is_alert:
        sev = "CRITICAL" if abs(b.bpm - 72) > 35 else "WARN"
        db.add(AlertEvent(alert_type="BPM_ALERT", severity=sev, source=b.node_id,
                          message=f"BPM={b.bpm:.0f} action={bpm_res.heal_action}"))
    await ws_mgr.broadcast({"type": "BIOMETRIC_UPDATE", "payload": {
        "node_id": b.node_id, "bpm": b.bpm, "spo2": b.spo2,
        "stress": b.stress_index, "alert": is_alert, "ts": b.timestamp.isoformat()
    }})
    return {"status": "ok", "alert": is_alert}

@app.get("/api/biometrics/recent", tags=["Biometrics"])
async def bio_recent(limit: int = Query(50, le=200), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(BiometricSample).order_by(desc(BiometricSample.id)).limit(limit))
    return [{"node": r.node_id, "bpm": r.bpm, "spo2": r.spo2,
             "alert": r.is_alert, "ts": r.timestamp.isoformat()} for r in rows.scalars()]


# ── Robotics ──────────────────────────────────────────────────────────────
@app.post("/api/robot/command", status_code=201, tags=["Robotics"])
async def robot_cmd(cmd: RobotCommandIn, db: AsyncSession = Depends(get_db)):
    db.add(RobotCommand(**cmd.model_dump(), executed=True))
    await ws_mgr.broadcast({"type": "ROBOT_CMD", "payload": cmd.model_dump()})
    return {"status": "dispatched", "command": cmd.command}

@app.get("/api/robot/commands", tags=["Robotics"])
async def robot_cmds(limit: int = Query(20, le=100), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(select(RobotCommand).order_by(desc(RobotCommand.id)).limit(limit))
    return [{"robot": r.robot_id, "cmd": r.command, "src": r.source,
             "zone": r.gaze_zone, "ts": r.timestamp.isoformat()} for r in rows.scalars()]


# ── Alerts ────────────────────────────────────────────────────────────────
@app.post("/api/alerts", status_code=201, tags=["Alerts"])
async def create_alert(alert: AlertIn, db: AsyncSession = Depends(get_db)):
    db.add(AlertEvent(**alert.model_dump()))
    await ws_mgr.broadcast({"type": "ALERT", "payload": alert.model_dump()})
    return {"status": "created"}

@app.get("/api/alerts", tags=["Alerts"])
async def list_alerts(resolved: bool = False, db: AsyncSession = Depends(get_db)):
    q = select(AlertEvent).where(AlertEvent.resolved == resolved).order_by(desc(AlertEvent.id)).limit(50)
    rows = await db.execute(q)
    return [{"id": r.id, "type": r.alert_type, "severity": r.severity,
             "source": r.source, "message": r.message, "ts": r.timestamp.isoformat()} for r in rows.scalars()]

@app.patch("/api/alerts/{aid}/resolve", tags=["Alerts"])
async def resolve_alert(aid: int, db: AsyncSession = Depends(get_db)):
    row = await db.get(AlertEvent, aid)
    if not row:
        raise HTTPException(404)
    row.resolved = True
    return {"status": "resolved"}


# ── Frontend Dashboard (serve last — catches all unmatched routes) ─────────
_frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "frontend")
if os.path.isdir(_frontend_dir):
    app.mount("/ui", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
