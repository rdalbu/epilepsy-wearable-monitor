import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Enum,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from .session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class CrisisStatus(str, enum.Enum):
    NORMAL = "NORMAL"
    MOVIMENTO_SUSPEITO = "MOVIMENTO_SUSPEITO"
    CRISE_CONFIRMADA = "CRISE_CONFIRMADA"


class Device(Base):
    __tablename__ = "devices"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False)

    telemetry = relationship("Telemetry", back_populates="device")
    crises = relationship("Crisis", back_populates="device")


class Telemetry(Base):
    __tablename__ = "telemetry"

    id = Column(String, primary_key=True, default=_uuid)
    device_id = Column(String, ForeignKey("devices.id"), index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    bpm = Column(Integer, nullable=False)
    baseline_bpm = Column(Integer, nullable=True)
    status = Column(Enum(CrisisStatus), nullable=False)

    device = relationship("Device", back_populates="telemetry")


class Crisis(Base):
    __tablename__ = "crises"

    id = Column(String, primary_key=True, default=_uuid)
    device_id = Column(String, ForeignKey("devices.id"), index=True, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    avg_bpm = Column(Integer, nullable=True)
    max_bpm = Column(Integer, nullable=True)

    device = relationship("Device", back_populates="crises")

