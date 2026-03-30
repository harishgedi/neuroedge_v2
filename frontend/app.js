/**
 * NeuroEdge v2 — Real-time Dashboard Controller
 * ================================================
 * Pure vanilla JS — no React, no Vue, no dependencies.
 * Connects via WebSocket for live streaming from FastAPI backend.
 * Polls REST endpoints for VNF and SLA state.
 *
 * Lightweight: <8KB unminified. Designed for minimal hardware.
 */

(() => {
    "use strict";

    // ── Config ────────────────────────────────────────────────────
    const WS_URL = `ws://${location.host}/ws/dashboard-${Date.now()}`;
    const API    = `${location.protocol}//${location.host}`;
    const MAX_FEED   = 40;
    const MAX_LATENCY = 60; // points per node in sparkline
    const POLL_INTERVAL = 4000;

    // ── State ─────────────────────────────────────────────────────
    let ws = null;
    let reconnectTimer = null;
    let anomalyTotal = 0;
    let healTotal = 0;
    const nodes = {};            // node_id → last telemetry
    const latencyHistory = {};   // node_id → [values]
    const bpmHistory = [];       // last 60 BPM values
    const edgeNodes = {};        // node_id → last telemetry
    let faceLandmarker;
    let runningMode = "IMAGE";
    let lastVideoTime = -1;
    let headPosition = { x: 0, y: 0 };
    let virtualCursor = { x: window.innerWidth / 2, y: window.innerHeight / 2 };
    let isTracking = false;
    let dwellStartTime = null;
    let dwellThreshold = 15; // pixels
    let dwellDuration = 1500; // ms
    let authorizedFaceDescriptor = null;
    let isAuthorized = false;
    let voiceRecognition = null;
    let isVoiceActive = false;
    let sensitivity = 0.5; // 0.0 to 1.0 (mapped from 1-100)
    let packetChart = null;
    let packetHistory = []; // TCP/UDP ratios
    const MAX_PACKETS = 40;

    // ── DOM Refs ──────────────────────────────────────────────────
    const $ = id => document.getElementById(id);

    // ── WebSocket ─────────────────────────────────────────────────
    function connect() {
        ws = new WebSocket(WS_URL);
        ws.onopen = () => {
            $("ws-status").querySelector(".ws-dot").className = "ws-dot connected";
            $("ws-label").textContent = "Live";
            console.log("NeuroEdge v2.1 Online | Research Inspiration: Dr. Enda Fallon & Dr. Mary Giblin");
        };
        ws.onclose = () => {
            $("ws-status").querySelector(".ws-dot").className = "ws-dot error";
            $("ws-label").textContent = "Reconnecting…";
            clearTimeout(reconnectTimer);
            reconnectTimer = setTimeout(connect, 2000);
        };
        ws.onerror = () => ws.close();
        ws.onmessage = e => {
            try { handleMessage(JSON.parse(e.data)); }
            catch (_) { /* skip malformed */ }
        };
    }

    // ── Voice Assistance (Google Assistant style) ─────────────────
    function initVoice() {
        const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!Speech) { console.warn("Speech API not supported"); return; }
        
        voiceRecognition = new Speech();
        voiceRecognition.continuous = true;
        voiceRecognition.interimResults = false;
        voiceRecognition.lang = 'en-US';

        voiceRecognition.onresult = (e) => {
            const cmd = e.results[e.results.length - 1][0].transcript.toLowerCase();
            processVoiceCommand(cmd);
        };

        voiceRecognition.onerror = () => stopVoice();
        voiceRecognition.onend = () => isVoiceActive && voiceRecognition.start();
    }

    function toggleVoice() {
        if (isVoiceActive) stopVoice();
        else startVoice();
    }

    function startVoice() {
        if (!voiceRecognition) initVoice();
        voiceRecognition.start();
        isVoiceActive = true;
        $("btn-voice").textContent = "VOICE: LISTENING...";
        $("btn-voice").classList.add("voice-active");
    }

    function stopVoice() {
        if (voiceRecognition) voiceRecognition.stop();
        isVoiceActive = false;
        $("btn-voice").textContent = "VOICE: OFF";
        $("btn-voice").classList.remove("voice-active");
    }

    function processVoiceCommand(cmd) {
        console.log("Voice Cmd:", cmd);
        if (cmd.includes("start tracking") || cmd.includes("enable eye")) startTracking();
        if (cmd.includes("stop tracking") || cmd.includes("disable eye")) stopTracking();
        if (cmd.includes("center") || cmd.includes("origin")) $("btn-center").click();
        if (cmd.includes("heal") || cmd.includes("repair")) {
            addAnomalyFeed({ node_id: "VOICE_INTENT", message: "Automated network healing triggered via Voice Command", severity: "INFO" });
            fetch(API + "/api/vnf/heal-all", { method: 'POST' }).catch(() => {});
        }
    }
    // ── HeadMouse & Face Recognition ─────────────────────────────
    async function initVision() {
        try {
            const vision = await FilesetResolver.forVisionTasks("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision/wasm");
            faceLandmarker = await FaceLandmarker.createFromOptions(vision, {
                baseOptions: { modelAssetPath: "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task", delegate: "GPU" },
                outputFaceBlendshapes: true, runningMode: "VIDEO", numFaces: 1
            });
            console.log("MediaPipe Face Landmarker Loaded");

            // Load Face-API models
            await faceapi.nets.ssdMobilenetv1.loadFromUri('https://cdn.jsdelivr.net/npm/@vladmandic/face-api/model');
            await faceapi.nets.faceLandmark68Net.loadFromUri('https://cdn.jsdelivr.net/npm/@vladmandic/face-api/model');
            await faceapi.nets.faceRecognitionNet.loadFromUri('https://cdn.jsdelivr.net/npm/@vladmandic/face-api/model');
            console.log("Face-API Models Loaded");

                const authImg = $("auth-img");
                // Skipping pre-load to wait for user upload
                console.log("Waiting for User Face Profile Upload...");
            }
        } catch (e) { console.error("Vision Init Error:", e); }
    }

    async function startTracking() {
        if (!faceLandmarker) return;
        const video = $("webcam");
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
            video.srcObject = stream;
            video.addEventListener("loadeddata", predictWebcam);
            isTracking = true;
            $("btn-tracking").textContent = "STOP TRACKING";
            $("btn-tracking").classList.replace("primary", "danger");
        } catch (e) { alert("Webcam access denied or not found."); }
    }

    function stopTracking() {
        const video = $("webcam");
        if (video.srcObject) {
            video.srcObject.getTracks().forEach(t => t.stop());
            video.srcObject = null;
        }
        isTracking = false;
        $("btn-tracking").textContent = "TRACKING";
        $("btn-tracking").classList.replace("danger", "primary");
        $("virtual-cursor").style.display = "none";
    }

    // ── Image Reference Upload ────────────────────────────────────
    async function handleFileReference(e) {
        const file = e.target.files[0];
        if (!file) return;
        const img = await faceapi.bufferToImage(file);
        
        // Update dashboard UI
        $("auth-img").src = img.src;
        $("auth-status").textContent = "Analyzing Profile...";
        $("auth-status").className = "value";

        const detection = await faceapi.detectSingleFace(img).withFaceLandmarks().withFaceDescriptor();
        if (detection) {
            authorizedFaceDescriptor = detection.descriptor;
            $("match-score").textContent = "SYNCED";
            $("btn-tracking").disabled = false; // Enable step 2
            $("auth-status").textContent = "Profile Ready";
            $("auth-status").className = "value status-granted";
            console.log("EyeWriter Gaze Reference Updated from Upload");
            addAnomalyFeed({ node_id: "SYSTEM", message: "Operator Profile Loaded Successfully", severity: "INFO" });
        } else {
            alert("Face not detected. Try a clearer portrait.");
        }
    }

    async function predictWebcam() {
        const video = $("webcam");
        const canvas = $("output-canvas");
        const ctx = canvas.getContext("2d");
        if (!isTracking) return;

        if (video.currentTime !== lastVideoTime) {
            lastVideoTime = video.currentTime;
            const result = faceLandmarker.detectForVideo(video, performance.now());
            
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            if (result.faceLandmarks && result.faceLandmarks.length > 0) {
                const landmarks = result.faceLandmarks[0];
                drawEyeWriterUI(ctx, landmarks, canvas.width, canvas.height);
                processEyeWriterMovement(landmarks);
                
                // Recognition every 2 seconds
                if (Math.floor(video.currentTime) % 2 === 0 && !isAuthorized) {
                    performFaceRecognition(video);
                }
            }
        }
        window.requestAnimationFrame(predictWebcam);
    }

    function drawEyeWriterUI(ctx, landmarks, w, h) {
        // Red Box (Face Bounds - Viola-Jones / Haar-like context)
        let minX = w, maxX = 0, minY = h, maxY = 0;
        landmarks.forEach(pt => {
            const x = pt.x * w; const y = pt.y * h;
            if (x < minX) minX = x; if (x > maxX) maxX = x;
            if (y < minY) minY = y; if (y > maxY) maxY = y;
        });
        
        ctx.strokeStyle = "var(--danger)";
        ctx.lineWidth = 2;
        ctx.strokeRect(minX - 10, minY - 10, (maxX - minX) + 20, (maxY - minY) + 20);

        // Green Box (ROI - centered 60%)
        const rw = (maxX - minX) * 0.6;
        const rh = (maxY - minY) * 0.6;
        const rx = minX + (maxX - minX) * 0.2;
        const ry = minY + (maxY - minY) * 0.2;
        ctx.strokeStyle = "var(--success)";
        ctx.strokeRect(rx, ry, rw, rh);

        // Feature Markers (Green Circles - selective)
        ctx.fillStyle = "var(--success)";
        [1, 4, 33, 263, 61, 291, 199, 10, 152].forEach(idx => {
            const pt = landmarks[idx];
            ctx.beginPath();
            ctx.arc(pt.x * w, pt.y * h, 3, 0, Math.PI * 2);
            ctx.fill();
        });

        // FPS Calculation
        const now = performance.now();
        if (!this.lastFrameTime) this.lastFrameTime = now;
        const fps = Math.round(1000 / (now - this.lastFrameTime));
        this.lastFrameTime = now;
        $("cam-fps").textContent = fps;
        $("cam-res").textContent = `${w}x${h}`;
    }

    function processEyeWriterMovement(landmarks) {
        if (!$("chk-move").checked) return;
        
        // Use Nose Tip (index 4) and bridge (index 1) for movement
        // Sensitivity Scaling (0.1 to 2.0x)
        const scaleX = (sensitivity * 2) + 0.1;
        const scaleY = (sensitivity * 2) + 0.1;

        // Apply scaling to movement relative to center
        const centerX = window.innerWidth / 2;
        const centerY = window.innerHeight / 2;
        const offsetX = targetX - centerX;
        const offsetY = targetY - centerY;

        virtualCursor.x += (centerX + (offsetX * scaleX) - virtualCursor.x) * 0.15;
        virtualCursor.y += (centerY + (offsetY * scaleY) - virtualCursor.y) * 0.15;

        const el = $("virtual-cursor");
        el.style.display = "block";
        el.style.left = virtualCursor.x + "px";
        el.style.top = virtualCursor.y + "px";

        checkDwellClick();
    }

    function checkDwellClick() {
        if (!$("chk-click").checked) return;

        const dist = Math.sqrt(Math.pow(virtualCursor.x - (this.lastX || 0), 2) + Math.pow(virtualCursor.y - (this.lastY || 0), 2));
        if (dist < dwellThreshold) {
            if (!dwellStartTime) dwellStartTime = Date.now();
            const elapsed = Date.now() - dwellStartTime;
            
            if (elapsed > dwellDuration) {
                triggerClick();
                dwellStartTime = Date.now() + 500; // delay persistent clicks
            }
        } else {
            dwellStartTime = null;
            document.body.classList.remove("clicking");
        }
        this.lastX = virtualCursor.x;
        this.lastY = virtualCursor.y;
    }

    function triggerClick() {
        document.body.classList.add("clicking");
        const el = document.elementFromPoint(virtualCursor.x, virtualCursor.y);
        if (el) {
            el.click();
            // HeadMouse click sound or visual feel
            const clickEvent = new MouseEvent("click", {
                bubbles: true, cancelable: true, view: window,
                clientX: virtualCursor.x, clientY: virtualCursor.y
            });
            el.dispatchEvent(clickEvent);
        }
        setTimeout(() => document.body.classList.remove("clicking"), 200);
    }

    async function performFaceRecognition(video) {
        if (!authorizedFaceDescriptor) return;
        const detection = await faceapi.detectSingleFace(video).withFaceLandmarks().withFaceDescriptor();
        if (detection) {
            const distance = faceapi.euclideanDistance(detection.descriptor, authorizedFaceDescriptor);
            const score = (1 - distance) * 100;
            $("match-score").textContent = Math.round(score) + "%";
            
            if (distance < 0.55) {
                isAuthorized = true;
                $("auth-status").textContent = "Authorized";
                $("auth-status").className = "value status-granted";
                $("op-id").textContent = "Harish Gedi (Dev)";
            }
        }
    }

    // ── Message Router ────────────────────────────────────────────
    function handleMessage(msg) {
        switch (msg.type) {
            case "HEARTBEAT":       updateHeartbeat(msg.payload); break;
            case "NETWORK_UPDATE":  updateNetwork(msg.payload);   break;
            case "GAZE_UPDATE":     updateGaze(msg.payload);      break;
            case "BIOMETRIC_UPDATE":updateBio(msg.payload);       break;
            case "ROBOT_CMD":       updateRobotCmd(msg.payload);  break;
            case "ALERT":           addAlert(msg.payload);        break;
            case "EDGE_UPDATE":     updateEdgeNode(msg.payload);  break;
            case "MOBILE_GAZE":     handleMobileGaze(msg.payload);break;
            case "SW_HEALTH":       handleHealthAlert(msg.payload);break;
            case "VNF_HEALING":     /* handled by poll */          break;
        }
    }

    function handleMobileGaze(p) {
        // Shared virtual cursor controlled by mobile
        virtualCursor.x += p.dx * (sensitivity * 50);
        virtualCursor.y += p.dy * (sensitivity * 50);
        $("virtual-cursor").style.left = virtualCursor.x + "px";
        $("virtual-cursor").style.top = virtualCursor.y + "px";
        if (p.click) triggerClick();
    }

    function handleHealthAlert(p) {
        if (p.spo2 < 90 || p.bpm < 50) {
            addAlert({ alert_type: "HEALTH_CRITICAL", severity: "CRITICAL", message: `Mobile/Node ${p.node_id} Critical Health detected!` });
        }
    }

    // ── Heartbeat (KPI bar) ───────────────────────────────────────
    function updateHeartbeat(p) {
        const relPct = ((p.reliability || 0) * 100).toFixed(3);
        $("kpi-rel-value").textContent = relPct + "%";
        $("kpi-rel-fill").style.width  = Math.min(100, p.reliability * 100) + "%";

        const anomScore = (p.anomaly_score || 0).toFixed(3);
        $("kpi-anom-value").textContent = anomScore;
        $("kpi-anom-fill").style.width  = Math.min(100, p.anomaly_score * 33.3) + "%";

        const fat = (p.fatigue || 0);
        $("kpi-fat-value").textContent = (fat * 100).toFixed(1) + "%";
        $("kpi-fat-fill").style.width  = (fat * 100) + "%";

        $("kpi-votes-value").textContent = (p.anomaly_votes_last || 0) + "/3";
        $("uptime").textContent = "Uptime: " + formatUptime(p.uptime_s || 0);
        $("ws-clients").textContent = "Clients: " + (p.ws_clients || 0);

        // colour coding
        $("kpi-rel-value").style.color = p.reliability > 0.999 ? "var(--green)" : p.reliability > 0.95 ? "var(--yellow)" : "var(--red)";
        $("kpi-anom-value").style.color = p.anomaly_score < 0.3 ? "var(--green)" : p.anomaly_score < 1.0 ? "var(--yellow)" : "var(--red)";
        $("kpi-fat-value").style.color = fat < 0.4 ? "var(--green)" : fat < 0.7 ? "var(--yellow)" : "var(--red)";
    }

    // ── Network Nodes ─────────────────────────────────────────────
    function updateNetwork(p) {
        nodes[p.node_id] = p;
        if (!latencyHistory[p.node_id]) latencyHistory[p.node_id] = [];
        latencyHistory[p.node_id].push(p.latency_ms);
        if (latencyHistory[p.node_id].length > MAX_LATENCY) latencyHistory[p.node_id].shift();

        renderNodes();
        renderLatencyChart();

        if (p.is_anomaly) {
            anomalyTotal++;
            addAnomalyFeed(p);
        }
    }

    function renderNodes() {
        const grid = $("node-grid");
        const ids = Object.keys(nodes).sort();
        $("node-count").textContent = ids.length + " nodes";

        grid.innerHTML = ids.map(id => {
            const n = nodes[id];
            const cls = n.is_anomaly ? "node-card anomaly" : "node-card";
            const latClass = n.latency_ms > 100 ? "bad" : "";
            const lossClass = n.packet_loss > 0.01 ? "bad" : "";
            return `<div class="${cls}">
                <div class="node-id">${id}</div>
                <div class="node-gen">${n.network_gen} · ${n.slice_type}</div>
                <div class="node-stats">
                    <span class="${latClass}">${n.latency_ms.toFixed(1)}ms</span>
                    <span class="${lossClass}">loss ${(n.packet_loss * 100).toFixed(3)}%</span>
                    <span>${n.rssi_dbm.toFixed(0)}dBm</span>
                </div>
            </div>`;
        }).join("");
    }

    // ── Anomaly Feed ──────────────────────────────────────────────
    function addAnomalyFeed(p) {
        const feed = $("anomaly-feed");
        if (feed.querySelector(".empty-state")) feed.innerHTML = "";

        const voteCls = p.algo_votes >= 3 ? "votes-3" : "votes-2";
        const el = document.createElement("div");
        el.className = "feed-item";
        el.innerHTML = `
            <span class="feed-dot"></span>
            <span class="feed-time">${timeStr()}</span>
            <span class="feed-text">
                <b>${p.node_id}</b> lat=${p.latency_ms.toFixed(1)}ms loss=${(p.packet_loss*100).toFixed(3)}%
                <span class="feed-badge ${voteCls}">${p.algo_votes}/3 votes</span>
                ${p.heal_action ? `<span class="feed-badge warn">${p.heal_action}</span>` : ""}
            </span>`;
        feed.prepend(el);
        while (feed.children.length > MAX_FEED) feed.lastChild.remove();
        $("anomaly-count").textContent = anomalyTotal + " detected";
    }

    // ── Remote Edge Nodes ─────────────────────────────────────────
    function updateEdgeNode(p) {
        edgeNodes[p.node_id] = { ...p, last_update: Date.now() };
        renderEdgeNodes();
    }

    function renderEdgeNodes() {
        const grid = $("edge-node-grid");
        const ids = Object.keys(edgeNodes).filter(i => Date.now() - edgeNodes[i].last_update < 30000);
        $("edge-count").textContent = ids.length + " remote nodes";

        if (ids.length === 0) {
            grid.innerHTML = '<div class="empty-state">Scan QR or visit /ui/mobile.html on Android to join…</div>';
            return;
        }

        grid.innerHTML = ids.map(id => {
            const n = edgeNodes[id];
            const batClass = n.battery < 20 ? "bad" : "";
            const latClass = n.latency > 200 ? "bad" : "";
            return `<div class="node-card edge-node">
                <div class="node-id"><span class="ws-dot connected"></span> ${id.toUpperCase()}</div>
                <div class="node-gen">Network: ${n.network} · Latency: <span class="${latClass}">${n.latency}ms</span></div>
                <div class="node-stats">
                    <span class="${batClass}">⚡ ${n.battery}% Bat</span>
                    <span>🌀 ${n.accel} Accel</span>
                    <span style="color:var(--accent)">Live Stream</span>
                </div>
            </div>`;
        }).join("");
    }

    // ── Gaze Zone ─────────────────────────────────────────────────
    function updateGaze(p) {
        document.querySelectorAll(".gaze-cell").forEach(c => c.classList.remove("active"));
        const zone = p.zone || "C";
        const cell = $("gz-" + zone);
        if (cell) cell.classList.add("active");
        $("gaze-cmd").textContent = p.robot_cmd || "No command";
        $("gaze-fatigue").textContent = "Fatigue: " + ((p.fatigue || 0) * 100).toFixed(0) + "%";
    }

    // ── Biometrics ────────────────────────────────────────────────
    function updateBio(p) {
        $("bio-bpm").textContent  = (p.bpm || 0).toFixed(0);
        $("bio-spo2").textContent = (p.spo2 || 0).toFixed(1);
        $("bio-stress").textContent = (p.stress || 0).toFixed(2);

        $("bio-bpm").style.color = p.bpm > 100 || p.bpm < 55 ? "var(--red)" : "var(--green)";

        bpmHistory.push(p.bpm);
        if (bpmHistory.length > 60) bpmHistory.shift();
        renderBPMChart();
    }

    function updateRobotCmd(p) {
        if (p.command) $("gaze-cmd").textContent = p.command;
    }

    function addAlert(p) {
        // Alerts go to the anomaly feed too
        const feed = $("anomaly-feed");
        if (feed.querySelector(".empty-state")) feed.innerHTML = "";
        const el = document.createElement("div");
        el.className = "feed-item";
        const cls = p.severity === "CRITICAL" ? "critical" : "warn";
        el.innerHTML = `
            <span class="feed-dot"></span>
            <span class="feed-time">${timeStr()}</span>
            <span class="feed-text">[${p.alert_type}] ${p.message} <span class="feed-badge ${cls}">${p.severity}</span></span>`;
        feed.prepend(el);
    }

    // ── REST Polling (VNF + SLA + Heal) ───────────────────────────
    async function pollREST() {
        try {
            // VNF Fleet
            const vnfRes = await fetch(API + "/api/vnf");
            if (vnfRes.ok) {
                const vnfData = await vnfRes.json();
                renderVNF(vnfData);
            }
        } catch (_) { /* API not ready yet */ }

        try {
            // SLA
            const slaRes = await fetch(API + "/api/sla");
            if (slaRes.ok) {
                const sla = await slaRes.json();
                renderSLA(sla);
            }
        } catch (_) {}

        try {
            // Heal log
            const healRes = await fetch(API + "/api/vnf/heal-log");
            if (healRes.ok) {
                const h = await healRes.json();
                renderHealLog(h.heal_log || []);
            }
        } catch (_) {}
    }

    function renderVNF(data) {
        const grid = $("vnf-grid");
        const fleet = data.vnf_fleet || {};
        const ids = Object.keys(fleet).sort();
        $("vnf-count").textContent = `${ids.length} VNFs (${data.active||0} active)`;

        if (ids.length === 0) { grid.innerHTML = '<div class="empty-state">No VNFs registered</div>'; return; }
        grid.innerHTML = ids.map(id => {
            const v = fleet[id];
            const st = v.state || "UNKNOWN";
            return `<div class="vnf-card">
                <div class="vnf-id">${id}</div>
                <div class="vnf-state ${st}">${st}</div>
            </div>`;
        }).join("");
    }

    function renderSLA(sla) {
        if (sla.message) return; // no data yet
        // Try to extract breach rates from SLA data
        for (const [slice, el, arcEl] of [
            ["URLLC", "sla-urllc-pct", ".urllc-arc"],
            ["eMBB",  "sla-embb-pct",  ".embb-arc"],
            ["mMTC",  "sla-mmtc-pct",  ".mmtc-arc"]
        ]) {
            const info = sla[slice];
            if (info) {
                const rate = 1 - (info.breach_rate || 0);
                const pct = (rate * 100).toFixed(1);
                $(el).textContent = pct + "%";
                $(el).style.color = rate > 0.99 ? "var(--green)" : rate > 0.95 ? "var(--yellow)" : "var(--red)";
                const arc = document.querySelector(arcEl);
                if (arc) arc.setAttribute("stroke-dasharray", `${rate*100}, 100`);
            }
        }
    }

    function renderHealLog(log) {
        const feed = $("heal-feed");
        if (log.length === 0) return;
        healTotal = log.length;
        $("heal-count").textContent = healTotal + " actions";
        feed.innerHTML = log.slice(-20).reverse().map(h => `
            <div class="feed-item">
                <span class="feed-dot heal"></span>
                <span class="feed-time">${(h.ts||"").split("T")[1]?.slice(0,8) || "--"}</span>
                <span class="feed-text"><b>${h.node}</b> ${h.metric} → <span class="feed-badge warn">${h.action}</span> (${h.votes}/3)</span>
            </div>
        `).join("");
    }

    // ── Canvas: BPM Sparkline ─────────────────────────────────────
    function renderBPMChart() {
        const canvas = $("bpm-chart");
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        const w = canvas.width = canvas.offsetWidth;
        const h = canvas.height = 90;
        ctx.clearRect(0, 0, w, h);

        if (bpmHistory.length < 2) return;
        const min = Math.min(...bpmHistory) - 5;
        const max = Math.max(...bpmHistory) + 5;
        const range = max - min || 1;

        // Gradient fill
        const grad = ctx.createLinearGradient(0, 0, 0, h);
        grad.addColorStop(0, "rgba(239, 68, 68, 0.15)");
        grad.addColorStop(1, "rgba(239, 68, 68, 0.0)");

        ctx.beginPath();
        ctx.moveTo(0, h);
        bpmHistory.forEach((v, i) => {
            const x = (i / (bpmHistory.length - 1)) * w;
            const y = h - ((v - min) / range) * h;
            ctx.lineTo(x, y);
        });
        ctx.lineTo(w, h);
        ctx.fillStyle = grad;
        ctx.fill();

        // Line
        ctx.beginPath();
        bpmHistory.forEach((v, i) => {
            const x = (i / (bpmHistory.length - 1)) * w;
            const y = h - ((v - min) / range) * h;
            i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
        });
        ctx.strokeStyle = "#ef4444";
        ctx.lineWidth = 1.5;
        ctx.stroke();
    }

    // ── Canvas: Latency per-node sparkline ─────────────────────────
    function renderLatencyChart() {
        const canvas = $("latency-chart");
        if (!canvas) return;
        const ctx = canvas.getContext("2d");
        const w = canvas.width = canvas.offsetWidth;
        const h = canvas.height = 140;
        ctx.clearRect(0, 0, w, h);

        const colours = ["#06b6d4","#10b981","#f59e0b","#ef4444","#a78bfa","#6366f1","#ec4899","#14b8a6"];
        const ids = Object.keys(latencyHistory).sort();

        // Find global max for scale
        let globalMax = 100;
        ids.forEach(id => {
            const mx = Math.max(...(latencyHistory[id] || [1]));
            if (mx > globalMax) globalMax = mx;
        });
        globalMax *= 1.1;

        // Draw SLA lines
        [[10, "URLLC 10ms", "#06b6d4"], [100, "eMBB 100ms", "#10b981"]].forEach(([val, lbl, clr]) => {
            const y = h - (val / globalMax) * h;
            if (y > 0 && y < h) {
                ctx.setLineDash([4, 4]);
                ctx.strokeStyle = clr + "44";
                ctx.lineWidth = 1;
                ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
                ctx.setLineDash([]);
                ctx.fillStyle = clr + "88";
                ctx.font = "9px Inter, sans-serif";
                ctx.fillText(lbl, 4, y - 3);
            }
        });

        // Draw each node's line
        ids.forEach((id, idx) => {
            const data = latencyHistory[id];
            if (data.length < 2) return;
            ctx.beginPath();
            data.forEach((v, i) => {
                const x = (i / (data.length - 1)) * w;
                const y = h - (v / globalMax) * h;
                i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
            });
            ctx.strokeStyle = colours[idx % colours.length];
            ctx.lineWidth = 1.2;
            ctx.stroke();
        });

        // Legend
        ctx.font = "9px 'JetBrains Mono', monospace";
        ids.forEach((id, idx) => {
            const x = 4 + idx * (w / ids.length);
            ctx.fillStyle = colours[idx % colours.length];
            ctx.fillText(id.replace("node-", ""), x, h - 4);
        });
    }

    // ── Network Pulse Analyzer (Simulation logic) ──────────────────
    function runPacketSimulation() {
        const tcpStream = $("packet-stream-tcp");
        const udpStream = $("packet-stream-udp");
        
        setInterval(() => {
            // TCP stream bits
            const bit = document.createElement("div");
            bit.className = "packet-bit";
            bit.style.animationDuration = (Math.random() * 1 + 0.5) + "s";
            bit.style.background = Math.random() > 0.8 ? "var(--red)" : "var(--green)";
            tcpStream.appendChild(bit);
            if (tcpStream.children.length > 30) tcpStream.removeChild(tcpStream.firstChild);

            // UDP stream bits
            const ubit = document.createElement("div");
            ubit.className = "packet-bit";
            ubit.style.animationDuration = (Math.random() * 0.5 + 0.2) + "s";
            ubit.style.background = "var(--cyan)";
            udpStream.appendChild(ubit);
            if (udpStream.children.length > 30) udpStream.removeChild(ubit);

            // Stats update
            $("wifi-strength").textContent = `Signal: -${Math.floor(Math.random() * 20 + 30)}dBm`;
        }, 150);
    }

    // ── Utilities ─────────────────────────────────────────────────
    function timeStr() {
        return new Date().toLocaleTimeString("en-GB", { hour12: false });
    }
    function formatUptime(s) {
        const h = Math.floor(s / 3600);
        const m = Math.floor((s % 3600) / 60);
        const sec = s % 60;
        return `${h}h ${m}m ${sec}s`;
    }

    // ── Init ──────────────────────────────────────────────────────
    initVision();
    connect();
    runPacketSimulation();
    setInterval(pollREST, POLL_INTERVAL);
    setTimeout(pollREST, 1000); 

    $("btn-tracking").onclick = () => isTracking ? stopTracking() : startTracking();
    $("btn-voice").onclick = () => toggleVoice();
    $("range-sensitivity").oninput = (e) => sensitivity = e.target.value / 100;
    $("file-reference").onchange = (e) => handleFileReference(e);

    $("btn-center").onclick = () => {
        virtualCursor.x = window.innerWidth / 2;
        virtualCursor.y = window.innerHeight / 2;
    };

    window.addEventListener("resize", () => {
        renderLatencyChart();
        renderBPMChart();
    });
})();
