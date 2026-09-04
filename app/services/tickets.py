from datetime import datetime

from app.models.assignments import Assignment
from app.models.comments import Comment
from app.models.entities import HistoryEvent, Ticket, User
from app.models.enums import CATEGORIES, PRIORITIES, TicketStatus


class TicketService:
    def __init__(self) -> None:
        self._tickets: list[Ticket] = []
        self._assignments: list[Assignment] = []
        self._comments: list[Comment] = []
        self._next_id = 1
        self._next_comment_id = 1

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

    def find_by_id(self, ticket_id: int) -> Ticket | None:
        return self.by_id(ticket_id)

    def list_by_status(self, status: TicketStatus | str) -> list[Ticket]:
        ticket_status = TicketStatus(status)
        return [ticket for ticket in self._tickets if ticket.status is ticket_status]

    def assign_technician(self, ticket_id: int, technician_id: int) -> Assignment:
        ticket = self._require_ticket(ticket_id)
        ticket.assignee_id = technician_id
        ticket.updated_at = datetime.now().astimezone()

        assignment = Assignment(
            ticket_id=ticket_id,
            technician_id=technician_id,
        )
        self._assignments.append(assignment)
        self._record_history(
            ticket=ticket,
            action="assigned",
            actor_id=technician_id,
            details={"technician_id": technician_id},
        )
        return assignment

    def add_comment(self, ticket_id: int, author_id: int, body: str) -> Comment:
        ticket = self._require_ticket(ticket_id)
        comment = Comment(
            id=self._next_comment_id,
            ticket_id=ticket_id,
            author_id=author_id,
            body=body,
        )
        self._next_comment_id += 1
        self._comments.append(comment)
        ticket.comments.append(comment)
        ticket.updated_at = datetime.now().astimezone()
        self._record_history(
            ticket=ticket,
            action="commented",
            actor_id=author_id,
            details={"comment_id": comment.id},
        )
        return comment

    def assigned_to(self, technician_id: int) -> list[Ticket]:
        return [ticket for ticket in self._tickets if ticket.assignee_id == technician_id]

    def change_status(
        self,
        ticket_id: int,
        new_status: TicketStatus | str,
        actor: User,
    ) -> Ticket:
        ticket = self._require_ticket(ticket_id)
        if not actor.is_staff:
            raise PermissionError("Only staff users can change ticket status")
        if not ticket.is_open:
            raise ValueError("Ticket is closed or cancelled")

        previous_status = ticket.status
        ticket.status = TicketStatus(new_status)
        ticket.updated_at = datetime.now().astimezone()
        self._record_history(
            ticket=ticket,
            action="status_changed",
            actor_id=actor.id,
            details={
                "from_status": previous_status.value,
                "to_status": ticket.status.value,
            },
        )
        return ticket

    def _record_history(
        self,
        ticket: Ticket,
        action: str,
        actor_id: int,
        details: dict,
    ) -> HistoryEvent:
        event = HistoryEvent(
            ticket_id=ticket.id,
            actor_id=actor_id,
            action=action,
            details=details,
        )
        ticket.history.append(event)
        return event

    def _require_ticket(self, ticket_id: int) -> Ticket:
        ticket = self.by_id(ticket_id)
        if ticket is None:
            raise ValueError(f"Ticket {ticket_id} was not found")
        return ticket

    def _validate(self, title: str, category: str, priority: str) -> None:
        if len(title.strip()) < 3:
            raise ValueError("title is required")
        if category not in CATEGORIES:
            raise ValueError("category is invalid")
        if priority not in PRIORITIES:
            raise ValueError("priority is invalid")
