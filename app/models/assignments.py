from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Assignment:
    ticket_id: int
    technician_id: int
    assigned_at: datetime = field(default_factory=lambda: datetime.now().astimezone())
