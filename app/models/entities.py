from dataclasses import dataclass, field
from datetime import datetime

from app.domain.clock import now
from app.models.comments import Comment
from app.models.enums import Role, TicketStatus


# 22/10/2026 - Los ids de todas las entidades son None hasta que el repositorio
# guarda el objeto: PostgreSQL asigna la llave primaria, no Python.
@dataclass
class HistoryEvent:
    # None hasta que el repositorio guarda el objeto: la base asigna la llave.
    id: int | None = field(default=None, kw_only=True)
    ticket_id: int
    actor_id: int
    event_type: str
    detail: str = ""
    created_at: datetime = field(default_factory=now)

    @property
    def action(self) -> str:
        return self.event_type

    @property
    def details(self) -> str:
        return self.detail


@dataclass
class User:
    # None hasta que el repositorio guarda el objeto: la base asigna la llave.
    id: int | None = field(default=None, kw_only=True)
    name: str
    email: str
    role: Role = Role.REQUESTER

    @property
    def is_staff(self) -> bool:
        return Role(self.role) in {
            Role.TECHNICIAN,
            Role.SUPERVISOR,
            Role.ADMINISTRATOR,
        }


# 22/10/2026 - Ticket suma due_at (lo calcula el trigger SLA de la base) y usa
# el reloj unico del dominio para created_at/updated_at.
@dataclass
class Ticket:
    # None hasta que el repositorio guarda el objeto: la base asigna la llave.
    id: int | None = field(default=None, kw_only=True)
    title: str
    description: str
    category: str
    priority: str
    requester_id: int
    status: TicketStatus = TicketStatus.OPEN
    assignee_id: int | None = None
    comments: list[Comment] = field(default_factory=list)
    history: list[HistoryEvent] = field(default_factory=list)
    created_at: datetime = field(default_factory=now)
    updated_at: datetime = field(default_factory=now)
    # Lo calcula el trigger de la base segun la prioridad: Python solo lo lee.
    due_at: datetime | None = None

    @property
    def is_open(self) -> bool:
        return self.status not in (TicketStatus.CLOSED, TicketStatus.CANCELLED)

    @property
    def is_assigned(self) -> bool:
        return self.assignee_id is not None
    
