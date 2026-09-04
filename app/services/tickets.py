from app.models.entities import Ticket
from app.models.enums import CATEGORIES, PRIORITIES, TicketStatus


class TicketService:
    def __init__(self) -> None:
        self._tickets: list[Ticket] = []
        self._next_id = 1

    def create(
        self,
        title: str,
        description: str,
        category: str,
        priority: str,
        requester_id: int,
        status: TicketStatus | str = TicketStatus.OPEN,
    ) -> Ticket:
        trimmed_title = title.strip()
        self._validate(title=trimmed_title, category=category, priority=priority)

        ticket = Ticket(
            id=self._next_id,
            title=trimmed_title,
            description=description,
            category=category,
            priority=priority,
            requester_id=requester_id,
            status=TicketStatus(status),
        )
        self._tickets.append(ticket)
        self._next_id += 1
        return ticket

    def list(self) -> list[Ticket]:
        return list(self._tickets)

    def by_id(self, ticket_id: int) -> Ticket | None:
        for ticket in self._tickets:
            if ticket.id == ticket_id:
                return ticket
        return None

    def list_by_status(self, status: TicketStatus | str) -> list[Ticket]:
        ticket_status = TicketStatus(status)
        return [ticket for ticket in self._tickets if ticket.status is ticket_status]

    def _validate(self, title: str, category: str, priority: str) -> None:
        if len(title.strip()) < 3:
            raise ValueError("title is required")
        if category not in CATEGORIES:
            raise ValueError("category is invalid")
        if priority not in PRIORITIES:
            raise ValueError("priority is invalid")
