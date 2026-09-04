from datetime import datetime

from app.domain.errors import (
    PermissionDeniedError,
    TicketNotFoundError,
    ValidationError,
)
from app.domain.workflow import assert_transition
from app.models.assignments import Assignment
from app.models.comments import Comment
from app.models.entities import HistoryEvent, Ticket, User
from app.models.enums import CATEGORIES, PRIORITIES, Role, TicketStatus
from app.repositories.base import TicketRepository
from app.services.notifications import Notifier, NullNotifier
from app.services.users import UserService


class TicketService:
    def __init__(
        self,
        repository: TicketRepository,
        users: UserService,
        notifier: Notifier | None = None,
    ) -> None:
        self._repository = repository
        self._users = users
        self._notifier = notifier or NullNotifier()
        self._next_comment_id = 1
        self._next_event_id = 1

    def create(
        self,
        title: str,
        description: str,
        category: str,
        priority: str,
        requester: User | int | None = None,
        status: TicketStatus | str = TicketStatus.OPEN,
        requester_id: int | None = None,
    ) -> Ticket:
        trimmed_title = title.strip()
        self._validate(title=trimmed_title, category=category, priority=priority)
        resolved_requester_id = self._resolve_user_id(
            requester,
            fallback_id=requester_id,
            field="requester_id",
        )

        ticket = Ticket(
            id=self._repository.next_id(),
            title=trimmed_title,
            description=description,
            category=category,
            priority=priority,
            requester_id=resolved_requester_id,
            status=TicketStatus(status),
        )
        stored = self._repository.add(ticket)
        self._notify(
            user_id=resolved_requester_id,
            title="ticket_created",
            message=f"Ticket #{stored.id} was created",
        )
        return stored

    def list(
        self,
        status: TicketStatus | str | None = None,
        assignee_id: int | None = None,
        requester_id: int | None = None,
    ) -> list[Ticket]:
        return self._repository.list(
            status=status,
            assignee_id=assignee_id,
            requester_id=requester_id,
        )

    def require(self, ticket_id: int) -> Ticket:
        ticket = self._repository.by_id(ticket_id)
        if ticket is None:
            raise TicketNotFoundError(ticket_id)
        return ticket

    def by_id(self, ticket_id: int) -> Ticket | None:
        return self._repository.by_id(ticket_id)

    def find_by_id(self, ticket_id: int) -> Ticket | None:
        return self.by_id(ticket_id)

    def list_by_status(self, status: TicketStatus | str) -> list[Ticket]:
        return self.list(status=status)

    def assigned_to(self, technician_id: int) -> list[Ticket]:
        return self.list(assignee_id=technician_id)

    def assign(
        self,
        ticket_id: int,
        technician_id: int,
        actor: User | None = None,
    ) -> Ticket:
        ticket = self.require(ticket_id)
        self._ensure_open(ticket)
        technician = self._users.require(technician_id)
        if actor is not None and not actor.is_staff:
            raise PermissionDeniedError(
                "Only staff users can assign tickets",
                actor_id=actor.id,
                ticket_id=ticket_id,
            )
        if Role(technician.role) not in {Role.TECHNICIAN, Role.SUPERVISOR}:
            raise ValidationError(
                "assignee must be support staff",
                field="technician_id",
                technician_id=technician_id,
            )

        ticket.assignee_id = technician_id
        ticket.updated_at = self._now()
        self._record_history(
            ticket=ticket,
            event_type="assigned",
            actor_id=actor.id if actor is not None else technician_id,
            detail=f"assigned to {technician.name}",
        )
        self._notify(
            user_id=technician_id,
            title="ticket_assigned",
            message=f"Ticket #{ticket.id} was assigned to you",
        )
        return ticket

    def assign_technician(self, ticket_id: int, technician_id: int) -> Assignment:
        self.assign(ticket_id=ticket_id, technician_id=technician_id)
        return Assignment(ticket_id=ticket_id, technician_id=technician_id)

    def comment(
        self,
        ticket_id: int,
        author: User | int | None = None,
        body: str | None = None,
        author_id: int | None = None,
    ) -> Comment:
        ticket = self.require(ticket_id)
        self._ensure_open(ticket)
        resolved_author_id = self._resolve_user_id(
            author,
            fallback_id=author_id,
            field="author_id",
        )
        if body is None:
            raise ValidationError("comment body is required", field="body")
        trimmed_body = body.strip()
        if not trimmed_body:
            raise ValidationError("comment body is required", field="body")

        comment = Comment(
            id=self._next_comment_id,
            ticket_id=ticket_id,
            author_id=resolved_author_id,
            body=trimmed_body,
        )
        self._next_comment_id += 1
        ticket.comments.append(comment)
        ticket.updated_at = self._now()
        self._record_history(
            ticket=ticket,
            event_type="commented",
            actor_id=resolved_author_id,
            detail="comment added",
        )
        if resolved_author_id != ticket.requester_id:
            self._notify(
                user_id=ticket.requester_id,
                title="ticket_commented",
                message=f"Ticket #{ticket.id} has a new comment",
            )
        return comment

    def add_comment(self, ticket_id: int, author_id: int, body: str) -> Comment:
        return self.comment(ticket_id=ticket_id, author_id=author_id, body=body)

    def change_status(
        self,
        ticket_id: int,
        new_status: TicketStatus | str,
        actor: User,
    ) -> Ticket:
        ticket = self.require(ticket_id)
        if not actor.is_staff:
            raise PermissionDeniedError(
                "Only staff users can change ticket status",
                actor_id=actor.id,
                ticket_id=ticket_id,
            )

        target_status = TicketStatus(new_status)
        previous_status = ticket.status
        assert_transition(previous_status, target_status)
        ticket.status = target_status
        ticket.updated_at = self._now()
        self._record_history(
            ticket=ticket,
            event_type="status_changed",
            actor_id=actor.id,
            detail=ticket.status.value,
        )
        self._notify(
            user_id=ticket.requester_id,
            title="ticket_status_changed",
            message=f"Ticket #{ticket.id} changed to {ticket.status.value}",
        )
        return ticket

    def cancel(
        self,
        ticket_id: int,
        actor: User | int | None = None,
        requester_id: int | None = None,
    ) -> Ticket:
        ticket = self.require(ticket_id)
        resolved_requester_id = self._resolve_user_id(
            actor,
            fallback_id=requester_id,
            field="requester_id",
        )
        if ticket.requester_id != resolved_requester_id:
            raise PermissionDeniedError(
                "Only the requester who opened the ticket can cancel it",
                requester_id=resolved_requester_id,
                ticket_id=ticket_id,
            )

        previous_status = ticket.status
        assert_transition(previous_status, TicketStatus.CANCELLED)
        ticket.status = TicketStatus.CANCELLED
        ticket.updated_at = self._now()
        self._record_history(
            ticket=ticket,
            event_type="cancelled",
            actor_id=resolved_requester_id,
            detail="cancelled",
        )
        self._notify(
            user_id=resolved_requester_id,
            title="ticket_cancelled",
            message=f"Ticket #{ticket.id} was cancelled",
        )
        return ticket

    def _record_history(
        self,
        ticket: Ticket,
        event_type: str,
        actor_id: int,
        detail: str,
    ) -> HistoryEvent:
        event = HistoryEvent(
            id=self._next_event_id,
            ticket_id=ticket.id,
            actor_id=actor_id,
            event_type=event_type,
            detail=detail,
        )
        self._next_event_id += 1
        ticket.history.append(event)
        return event

    def _resolve_user_id(
        self,
        actor: User | int | None,
        fallback_id: int | None,
        field: str,
    ) -> int:
        if isinstance(actor, User):
            user_id = actor.id
        elif actor is not None:
            user_id = actor
        elif fallback_id is not None:
            user_id = fallback_id
        else:
            raise ValidationError(f"{field} is required", field=field)

        self._users.require(user_id)
        return user_id

    def _ensure_open(self, ticket: Ticket) -> None:
        if not ticket.is_open:
            raise ValidationError(
                "ticket is closed or cancelled",
                field="ticket",
                ticket_id=ticket.id,
            )

    def _validate(self, title: str, category: str, priority: str) -> None:
        if len(title.strip()) < 3:
            raise ValidationError("title is required", field="title")
        if category not in CATEGORIES:
            raise ValidationError("category is invalid", field="category")
        if priority not in PRIORITIES:
            raise ValidationError("priority is invalid", field="priority")

    def _notify(
        self,
        user_id: int,
        title: str,
        message: str,
    ) -> None:
        self._notifier.notify(user_id, title, message)

    def _now(self) -> datetime:
        return datetime.now().astimezone()
