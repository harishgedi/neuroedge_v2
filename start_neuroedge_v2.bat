@echo off
echo Starting NeuroEdge v2.1 Lite (Lite Architecture for Mobile/Ngrok)
echo =================================================================

:: Start FastAPI Hub
echo [1] Booting FastAPI API Hub for mobile pings...
start cmd /k "cd backend && pip install -r ../requirements.txt && uvicorn api.main:app --port 8000 --reload"

:: Wait for server to stabilize
timeout /t 5 /nobreak > NUL

:: Open Dashboards
echo [2] Launching Isolated Dashboards in Chrome...
start "" "frontend/eye_dashboard.html"
start "" "frontend/health_dashboard.html"

echo.
echo *** NeuroEdge v2.1 is now LIVE! ***
echo.
echo Next Steps for Demonstration:
echo 1. Start Ngrok: `ngrok http 8000`
echo 2. Run `sender.sh` on your Android phone using the Ngrok link.
echo 3. Watch the Health Dashboard react with live sensor signals!
echo.
pause
