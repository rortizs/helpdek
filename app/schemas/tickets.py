"""22/10/2026 - Esquemas (Pydantic) de tickets: lo que entra y sale por HTTP.

Son distintos de las entidades de dominio a proposito: el cliente solo puede
enviar titulo, descripcion, categoria y prioridad. El estado, el solicitante y
las fechas los decide el servidor.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from app.domain.clock import now
from app.models.enums import CATEGORIES, PRIORITIES, TicketStatus


class TicketCreate(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    description: str
    category: str
    priority: str

    @field_validator("category")
    @classmethod
    def category_must_exist(cls, value: str) -> str:
        if value not in CATEGORIES:
            raise ValueError(f"category must be one of: {', '.join(CATEGORIES)}")
        return value

    @field_validator("priority")
    @classmethod
    def priority_must_exist(cls, value: str) -> str:
        if value not in PRIORITIES:
            raise ValueError(f"priority must be one of: {', '.join(PRIORITIES)}")
        return value


class CommentCreate(BaseModel):
    # El autor no se recibe: es quien hace la peticion.
    body: str = Field(min_length=1)


class AssignRequest(BaseModel):
    technician_id: int


class StatusChange(BaseModel):
    status: TicketStatus


class PriorityChange(BaseModel):
    # Sin validar aqui: TicketService ya conoce las prioridades validas.
    priority: str


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    author_id: int
    body: str
    created_at: datetime


class HistoryEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    actor_id: int
    event_type: str
    detail: str
    created_at: datetime


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    category: str
    priority: str
    status: TicketStatus
    requester_id: int
    assignee_id: int | None
    created_at: datetime
    updated_at: datetime
    due_at: datetime | None

    @computed_field
    @property
    def is_overdue(self) -> bool:
        """Misma regla que la vista v_tickets_dashboard: solo vence lo que sigue activo."""
        active = self.status in (TicketStatus.OPEN, TicketStatus.IN_PROGRESS)
        return active and self.due_at is not None and self.due_at < now()


class TicketDetailOut(TicketOut):
    comments: list[CommentOut]
    history: list[HistoryEventOut]
