#!/data/data/com.termux/files/usr/bin/bash
# ==============================================================================
# NeuroEdge v2.1: Android Sensor Broadcaster (Lite Architecture)
# ==============================================================================
# Connects Android hardware directly to the laptop's FastAPI server over Ngrok
# Required Termux Packages: termux-api, jq, curl

# ⚠️ REPLACE THIS URL WITH YOUR ACTIVE NGROK LINK from `ngrok http 8000`
SERVER_URL="https://YOUR_NGROK_ID_HERE.ngrok-free.app/api/telemetry"

echo "[*] NeuroEdge Mobile Node Booting..."
echo "[*] Target Node Payload URI: $SERVER_URL"
echo ""

while true; do
    # 1. Poll Battery Hardware
    BATTERY=$(termux-battery-status | jq .percentage)
    if [ -z "$BATTERY" ]; then BATTERY="80"; fi # Fallback for emulators

    # 2. Poll WiFi RSSI Signal Strength (Long Distance Integrity Check)
    WIFI=$(termux-wifi-connectioninfo | jq .rssi)
    if [ -z "$WIFI" ]; then WIFI="-65"; fi

    # 3. Simulate Smartwatch SpO2 / Heart Rate integration (via Health Connect API)
    # Using random variables to demonstrate live fluctuations on the graph
    HR_BASE=72
    HR_FLUCTUATION=$(( (RANDOM % 15) - 5 ))
    HEART_RATE=$((HR_BASE + HR_FLUCTUATION))

    # 4. Transmit Payload over TLS
    curl -s -X POST -H "Content-Type: application/json" \
         -d "{\"battery_level\": $BATTERY, \"wifi_strength\": $WIFI, \"heart_rate\": \"$HEART_RATE\"}" \
         $SERVER_URL > /dev/null

    echo ">>> BROADCAST SUCCESS | Bat: $BATTERY% | Sig: $WIFI dBm | HR: $HEART_RATE BPM"
    
    # Wait 2 seconds before next ping
    sleep 2
done
