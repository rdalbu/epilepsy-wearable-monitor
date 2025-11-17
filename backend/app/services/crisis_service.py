from typing import Optional, Dict, Any

from sqlalchemy.orm import Session

from app.db.models import Crisis, Telemetry, CrisisStatus


def _get_open_crisis(db: Session, device_id: str) -> Optional[Crisis]:
    return (
        db.query(Crisis)
        .filter(Crisis.device_id == device_id, Crisis.end_time.is_(None))
        .order_by(Crisis.start_time.desc())
        .first()
    )


def process_telemetry_and_update_crisis(
    db: Session,
    telemetry: Telemetry,
) -> Optional[Dict[str, Any]]:
    """
    Atualiza o estado de crise com base na telemetria atual.
    Retorna um dicionário simples descrevendo o evento de crise, ou None.
    """
    crisis = _get_open_crisis(db, telemetry.device_id)

    # Início de crise
    if telemetry.status == CrisisStatus.CRISE_CONFIRMADA and crisis is None:
        crisis = Crisis(
            device_id=telemetry.device_id,
            start_time=telemetry.timestamp,
            max_bpm=telemetry.bpm,
        )
        db.add(crisis)
        db.flush()  # garante que crisis.id esteja disponível
        return {"type": "CRISIS_STARTED", "crisis_id": crisis.id}

    # Atualização de crise em andamento
    if crisis is not None:
        crisis.max_bpm = max(crisis.max_bpm or 0, telemetry.bpm)

        # Fim de crise quando status voltar para NORMAL
        if telemetry.status == CrisisStatus.NORMAL and crisis.end_time is None:
            crisis.end_time = telemetry.timestamp
            crisis.avg_bpm = crisis.max_bpm
            return {"type": "CRISIS_ENDED", "crisis_id": crisis.id}

    return None

