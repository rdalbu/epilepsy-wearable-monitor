from typing import List

from datetime import datetime

from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.session import Base, engine, get_db
from app.db.models import Device, Telemetry
from app.db.schemas import TelemetryIn, CrisisOut
from app.services.crisis_service import process_telemetry_and_update_crisis


Base.metadata.create_all(bind=engine)

app = FastAPI(title="Epilepsy Monitor API")

origins = [
    "http://localhost:5173",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

active_dashboards: List[WebSocket] = []


@app.post("/api/telemetry")
async def receive_telemetry(payload: TelemetryIn, db: Session = Depends(get_db)):
    # Garante que o device exista (simplificado)
    device = db.query(Device).filter(Device.id == payload.device_id).first()
    if device is None:
        device = Device(id=payload.device_id, name=payload.device_id)
        db.add(device)
        db.flush()

    telemetry = Telemetry(
        device_id=payload.device_id,
        timestamp=payload.timestamp,
        bpm=payload.bpm,
        baseline_bpm=payload.baseline_bpm,
        status=payload.status,
    )
    db.add(telemetry)

    crisis_event = process_telemetry_and_update_crisis(db, telemetry)
    db.commit()

    data_for_front = {
        "device_id": payload.device_id,
        "timestamp": payload.timestamp.isoformat(),
        "bpm": payload.bpm,
        "baseline_bpm": payload.baseline_bpm,
        "status": payload.status.value,
        "crisis_event": crisis_event,
    }

    to_remove: List[WebSocket] = []
    for ws in active_dashboards:
        try:
            await ws.send_json(data_for_front)
        except Exception:
            to_remove.append(ws)
    for ws in to_remove:
        if ws in active_dashboards:
            active_dashboards.remove(ws)

    return JSONResponse({"ok": True})


@app.get("/api/crises", response_model=List[CrisisOut])
def list_crises(device_id: str, db: Session = Depends(get_db)):
    from app.db.models import Crisis

    crises = (
        db.query(Crisis)
        .filter(Crisis.device_id == device_id)
        .order_by(Crisis.start_time.desc())
        .all()
    )
    return crises


@app.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket):
    await websocket.accept()
    active_dashboards.append(websocket)
    try:
        while True:
            # Mantém a conexão viva; ignoramos mensagens de entrada por enquanto
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in active_dashboards:
            active_dashboards.remove(websocket)


@app.get("/health")
def health_check():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}

