from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from .models import CrisisStatus


class TelemetryIn(BaseModel):
    device_id: str = Field(..., example="bracelet-01")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    bpm: int
    baseline_bpm: Optional[int] = None
    status: CrisisStatus


class CrisisOut(BaseModel):
    id: str
    device_id: str
    start_time: datetime
    end_time: Optional[datetime]
    avg_bpm: Optional[int]
    max_bpm: Optional[int]

    class Config:
        orm_mode = True

