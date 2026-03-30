import { FaceLandmarker, FilesetResolver } from "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.33/vision_bundle.mjs";

const state = {
    battery: 0,
    rtt: 0,
    accel: { x: 0, y: 0, z: 0 },
    heartRate: 72,
    lastUpdate: null,
    isRunning: false,
    isVisionRunning: false,
    serverUrl: "/api/telemetry",
    gazeUrl: "/api/gaze/remote"
};

let faceLandmarker;
let lastVideoTime = -1;

// UI Elements
const els = {
    overlay: document.getElementById('overlay'),
    initBtn: document.getElementById('init-btn'),
    toggleVision: document.getElementById('toggle-vision'),
    visionStatus: document.getElementById('vision-status'),
    webcam: document.getElementById('mobile-webcam'),
    canvas: document.getElementById('vision-canvas'),
    valBattery: document.getElementById('val-battery'),
    valNet: document.getElementById('val-net'),
    valType: document.getElementById('val-type'),
    valAcc: document.getElementById('val-acc'),
    valHeart: document.getElementById('val-heart'),
    pulse: document.getElementById('pulse'),
    logs: document.getElementById('logs'),
    bars: {
        x: document.getElementById('bar-x'),
        y: document.getElementById('bar-y'),
        z: document.getElementById('bar-z')
    }
};

function log(msg) {
    const time = new Date().toLocaleTimeString();
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerHTML = `<span class="log-time">[${time}]</span> ${msg}`;
    els.logs.prepend(entry);
    if (els.logs.children.length > 5) els.logs.lastElementChild.remove();
}

async function initSensors() {
    log("INITIALIZING_SENSORS...");
    
    // 1. Battery API
    if ('getBattery' in navigator) {
        const battery = await navigator.getBattery();
        const updateBattery = () => {
            state.battery = Math.round(battery.level * 100);
            els.valBattery.innerHTML = `${state.battery}<span class="unit">%</span>`;
        };
        battery.addEventListener('levelchange', updateBattery);
        updateBattery();
    }

    // 2. Network Information API
    if ('connection' in navigator) {
        const conn = navigator.connection;
        const updateNet = () => {
            state.rtt = conn.rtt || 50;
            els.valNet.innerHTML = `${state.rtt}<span class="unit">ms</span>`;
            els.valType.innerText = `NET_TYPE: ${conn.effectiveType.toUpperCase()}`;
        };
        conn.addEventListener('change', updateNet);
        updateNet();
    }

    // 3. Device Motion (Accelerometer)
    if (window.DeviceMotionEvent) {
        window.addEventListener('devicemotion', (event) => {
            const acc = event.accelerationIncludingGravity;
            if (acc) {
                state.accel.x = acc.x || 0;
                state.accel.y = acc.y || 0;
                state.accel.z = acc.z || 0;

                const avg = (Math.abs(acc.x) + Math.abs(acc.y) + Math.abs(acc.z)) / 3;
                els.valAcc.innerText = avg.toFixed(1);

                // Update Visualizer Bars
                els.bars.x.style.height = `${Math.min(100, Math.abs(acc.x) * 10)}%`;
                els.bars.y.style.height = `${Math.min(100, Math.abs(acc.y) * 10)}%`;
                els.bars.z.style.height = `${Math.min(100, Math.abs(acc.z) * 10)}%`;
                
                // Colorize bars if high motion
                const color = avg > 5 ? '#ff0055' : '#00f0ff';
                Object.values(els.bars).forEach(b => b.style.background = color);
            }
        });
    }

    // 4. Heart Rate Simulator (Health Connect Sync Proxy)
    setInterval(() => {
        const fluct = Math.floor(Math.random() * 6) - 3;
        state.heartRate = Math.max(60, Math.min(120, state.heartRate + fluct));
        els.valHeart.innerText = state.heartRate;
    }, 2000);

    state.isRunning = true;
    startTelemetryLoop();
}

async function initVision() {
    try {
        els.visionStatus.innerText = "STATUS: LOADING_MODELS...";
        const filesetResolver = await FilesetResolver.forVisionTasks("https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.33/wasm");
        faceLandmarker = await FaceLandmarker.createFromOptions(filesetResolver, {
            baseOptions: { 
                modelAssetPath: `https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task`, 
                delegate: "GPU" 
            },
            outputFaceBlendshapes: false,
            runningMode: "VIDEO",
            numFaces: 1
        });

        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user" } });
        els.webcam.srcObject = stream;
        
        els.webcam.addEventListener("loadeddata", () => {
            state.isVisionRunning = true;
            els.visionStatus.innerText = "STATUS: BROADCASTING_GAZE";
            els.toggleVision.innerText = "DEACTIVATE";
            requestAnimationFrame(visionLoop);
        });
    } catch(e) {
        els.visionStatus.innerText = "STATUS: HARDWARE_ERROR";
        console.error(e);
    }
}

async function visionLoop() {
    if (!state.isVisionRunning) return;
    
    if (els.webcam.currentTime !== lastVideoTime && faceLandmarker) {
        const results = faceLandmarker.detectForVideo(els.webcam, performance.now());
        if (results.faceLandmarks && results.faceLandmarks.length > 0) {
            const nose = results.faceLandmarks[0][1]; 
            
            // Scaled coordinates
            const x = (1 - nose.x);
            const y = nose.y;

            // Transmit Remote Gaze to Laptop
            broadcastRemoteGaze(x, y);
        }
        lastVideoTime = els.webcam.currentTime;
    }
    requestAnimationFrame(visionLoop);
}

async function broadcastRemoteGaze(x, y) {
    try {
        await fetch(state.gazeUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ x, y })
        });
    } catch(e) {}
}

async function startTelemetryLoop() {
    log("BROADCAST_START: TARGETING_LOCAL_HUB");
    
    while (state.isRunning) {
        try {
            const payload = {
                battery_level: state.battery,
                wifi_strength: -30 - (state.rtt / 10), // Heuristic: RSSI estimated from RTT
                heart_rate: state.heartRate,
                accel_avg: parseFloat(els.valAcc.innerText),
                ts: new Date().toISOString()
            };

            const response = await fetch(state.serverUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (response.ok) {
                // Trigger Pulse
                els.pulse.classList.remove('pulse-anim');
                void els.pulse.offsetWidth; // Force reflow
                els.pulse.classList.add('pulse-anim');
            }
        } catch (e) {
            log("CONNECTION_LOST: RETRYING...");
        }
        await new Promise(r => setTimeout(r, 2000));
    }
}

// User Interaction Required for Sensors
els.initBtn.addEventListener('click', () => {
    els.overlay.style.opacity = '0';
    setTimeout(() => {
        els.overlay.style.display = 'none';
        initSensors();
    }, 500);
});

els.toggleVision.addEventListener('click', () => {
    if (!state.isVisionRunning) {
        initVision();
    } else {
        state.isVisionRunning = false;
        els.visionStatus.innerText = "STATUS: STANDBY";
        els.toggleVision.innerText = "ACTIVATE";
        const stream = els.webcam.srcObject;
        if (stream) stream.getTracks().forEach(t => t.stop());
    }
});
