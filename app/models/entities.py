from dataclasses import dataclass, field
from datetime import datetime

from app.models.comments import Comment
from app.models.enums import Role, TicketStatus


@dataclass
class HistoryEvent:
    id: int
    ticket_id: int
    actor_id: int
    event_type: str
    detail: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now().astimezone())

    @property
    def action(self) -> str:
        return self.event_type

    @property
    def details(self) -> str:
        return self.detail


@dataclass
class User:
    id: int
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


@dataclass
class Ticket:
    id: int
    title: str
    description: str
    category: str
    priority: str
    requester_id: int
    status: TicketStatus = TicketStatus.OPEN
    assignee_id: int | None = None
    comments: list[Comment] = field(default_factory=list)
    history: list[HistoryEvent] = field(default_factory=list)
    created_at: datetime = field(
        default_factory=lambda: datetime.now().astimezone()
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now().astimezone()
    )

    @property
    def is_open(self) -> bool:
        return self.status not in (TicketStatus.CLOSED, TicketStatus.CANCELLED)

    @property
    def is_assigned(self) -> bool:
        return self.assignee_id is not None
