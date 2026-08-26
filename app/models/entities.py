from dataclasses import dataclass, field
from datetime import datetime

from app.models.enums import Role, TicketStatus

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
    created_at: datetime = field(default_factory=datetime.astimezone)
    updated_at: datetime = field(default_factory=datetime.astimezone)