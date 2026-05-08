@echo off
echo [*] Starting LeadStation Backend...
cd /d "%~dp0"
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
pause
