@echo off
REM Inicia backend, frontend e bridge serial em janelas separadas

cd /d "%~dp0"

REM Backend (FastAPI)
start "Epilepsy Backend" cmd /k "cd /d backend && python -m uvicorn app.main:app --reload --port 8000"

REM Frontend (React)
start "Epilepsy Frontend" cmd /k "cd /d frontend && npm run dev"

REM Bridge Serial (COM -> backend)
start "Serial Bridge" cmd /k "cd /d backend && python serial_bridge.py"

