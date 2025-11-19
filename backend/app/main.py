from typing import Dict, List
from datetime import datetime

from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import Base, engine, get_db
from app.db.models import Device, Telemetry
from app.db.schemas import TelemetryIn, CrisisOut
from app.services.crisis_service import process_telemetry_and_update_crisis


# Cria as tabelas no banco (se ainda não existirem)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Epilepsy Monitor API")

# Origens permitidas para o frontend
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

# Lista de dashboards conectados via WebSocket
active_dashboards: List[WebSocket] = []


class DeviceConfig(BaseModel):
    device_id: str
    use_hr_check: bool


# Configuração em memória por device_id
device_configs: Dict[str, bool] = {}


@app.post("/api/telemetry")
async def receive_telemetry(payload: TelemetryIn, db: Session = Depends(get_db)):
    """
    Recebe telemetria da pulseira, registra no banco,
    atualiza o estado de crise e notifica os dashboards via WebSocket.
    """
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

    # Atualiza/abre/fecha crise conforme a regra de negócio
    crisis_event = process_telemetry_and_update_crisis(db, telemetry)
    db.commit()

    # Payload enviado em tempo real para os dashboards conectados
    data_for_front = {
        "device_id": payload.device_id,
        "timestamp": payload.timestamp.isoformat(),
        "bpm": payload.bpm,
        "baseline_bpm": payload.baseline_bpm,
        "status": payload.status.value,
        "crisis_event": crisis_event,
    }

    # Envia para todos dashboards conectados
    to_remove: List[WebSocket] = []
    for ws in active_dashboards:
        try:
            await ws.send_json(data_for_front)
        except Exception:
            to_remove.append(ws)

    # Remove websockets desconectados
    for ws in to_remove:
        if ws in active_dashboards:
            active_dashboards.remove(ws)

    return JSONResponse({"ok": True})


@app.get("/api/crises", response_model=List[CrisisOut])
def list_crises(device_id: str, db: Session = Depends(get_db)):
    """
    Lista crises registradas para um device específico.
    """
    from app.db.models import Crisis

    crises = (
        db.query(Crisis)
        .filter(Crisis.device_id == device_id)
        .order_by(Crisis.start_time.desc())
        .all()
    )
    return crises


@app.post("/api/device-config", response_model=DeviceConfig)
def set_device_config(config: DeviceConfig) -> DeviceConfig:
    """
    Define a configuração de uso da checagem de batimentos por device.
    """
    device_configs[config.device_id] = config.use_hr_check
    return config


@app.get("/api/device-config", response_model=DeviceConfig)
def get_device_config(device_id: str) -> DeviceConfig:
    """
    Retorna a configuração de uso de batimento para o device.
    IMPORTANTE: default agora é False, para não travar a confirmação
    de crise enquanto o BPM ainda não estiver calibrado.
    """
    # ANTES era True, o que ligava o filtro de batimento e impedia
    # a crise de ser confirmada enquanto o BPM estava 0.
    use_hr = device_configs.get(device_id, False)
    return DeviceConfig(device_id=device_id, use_hr_check=use_hr)


@app.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket):
    """
    WebSocket usado pelo dashboard para receber dados em tempo real.
    """
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
    """
    Health-check simples da API.
    """
    return {"status": "ok", "time": datetime.utcnow().isoformat()}
