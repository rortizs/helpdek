"""22/10/2026 - Esquemas de avisos (notificaciones) que salen por HTTP."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int | None
    title: str
    message: str
    type: str
    read_at: datetime | None
    created_at: datetime


class ReadAllOut(BaseModel):
    updated: int
