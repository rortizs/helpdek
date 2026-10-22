"""22/10/2026 - Reglas de negocio de los tickets.

TicketService no sabe donde se guardan los datos ni a quien se avisa: recibe un
repositorio y un notifier. Los ids los asigna el repositorio al guardar, por eso
el servicio ya no lleva contadores propios (semana 13).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from app.domain.clock import now
from app.domain.errors import (
    PermissionDeniedError,
    TicketNotFoundError,
    ValidationError,
)
from app.domain.events import (
    TicketAssigned,
    TicketCancelled,
    TicketCommented,
    TicketCreated,
    TicketEvent,
    TicketStatusChanged,
)
from app.domain.workflow import assert_transition
from app.models.assignments import Assignment
from app.models.comments import Comment
from app.models.entities import HistoryEvent, Ticket, User
from app.models.enums import CATEGORIES, PRIORITIES, Role, TicketStatus
from app.repositories.base import TicketPage, TicketQuery, TicketRepository
from app.services.events import EventPublisher, TicketEventSubscriber
from app.services.notifications import Notifier, NotifierSubscriber, NullNotifier
from app.services.users import UserService


class TicketService:
    """22/10/2026 - Casos de uso de tickets: crear, asignar, comentar, cambiar estado y prioridad.

    Semana 15: ya no llama al notificador directamente. Cada caso de uso publica un
    evento de dominio y quien quiera reaccionar (avisos, auditoria...) se suscribe.
    """

    def __init__(
        self,
        repository: TicketRepository,
        users: UserService,
        notifier: Notifier | None = None,
        subscribers: Iterable[TicketEventSubscriber] = (),
    ) -> None:
        self._repository = repository
        self._users = users
        self._events = EventPublisher()
        # 22/10/2026 - Compatibilidad: el parametro `notifier` de las semanas 7-13
        # sigue funcionando; ahora solo se envuelve como un suscriptor mas.
        self._events.subscribe(NotifierSubscriber(notifier or NullNotifier()))
        for subscriber in subscribers:
            self._events.subscribe(subscriber)

    def subscribe(self, subscriber: TicketEventSubscriber) -> None:
        """22/10/2026 - Agrega un suscriptor despues de construir el servicio."""
        self._events.subscribe(subscriber)

    def unsubscribe(self, subscriber: TicketEventSubscriber) -> None:
        """22/10/2026 - Da de baja un suscriptor."""
        self._events.unsubscribe(subscriber)

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
            title=trimmed_title,
            description=description,
            category=category,
            priority=priority,
            requester_id=resolved_requester_id,
            status=TicketStatus(status),
        )
        stored = self._repository.add(ticket)
        self._publish(
            TicketCreated(
                ticket_id=stored.id,
                actor_id=resolved_requester_id,
                requester_id=resolved_requester_id,
            )
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

    def list_for(
        self,
        actor: User,
        status: TicketStatus | str | None = None,
        category: str | None = None,
        priority: str | None = None,
        assignee_id: int | None = None,
        requester_id: int | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> TicketPage:
        """22/10/2026 - Lista lo que `actor` puede ver: el personal todo, un solicitante lo suyo."""
        if category is not None and category not in CATEGORIES:
            raise ValidationError("category is invalid", field="category")
        if priority is not None and priority not in PRIORITIES:
            raise ValidationError("priority is invalid", field="priority")
        if not actor.is_staff:
            # Pedir los tickets de otra persona no da error ni los revela: da vacio.
            if requester_id not in (None, actor.id):
                return TicketPage()
            requester_id = actor.id
        return self._repository.search(
            TicketQuery(
                status=status,
                category=category,
                priority=priority,
                assignee_id=assignee_id,
                requester_id=requester_id,
                limit=limit,
                offset=offset,
            )
        )

    def require(self, ticket_id: int) -> Ticket:
        ticket = self._repository.by_id(ticket_id)
        if ticket is None:
            raise TicketNotFoundError(ticket_id)
        return ticket

    def require_for(self, actor: User, ticket_id: int) -> Ticket:
        """22/10/2026 - Como require(), pero un ticket ajeno "no existe" para un solicitante."""
        ticket = self.require(ticket_id)
        self._ensure_visible(ticket, actor)
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
        # El permiso se revisa ANTES de buscar el ticket: quien no es personal
        # recibe 403 igual exista o no, asi no se averigua que ids existen.
        if actor is not None and not actor.is_staff:
            raise PermissionDeniedError(
                "Only staff users can assign tickets",
                actor_id=actor.id,
                ticket_id=ticket_id,
            )
        ticket = self.require(ticket_id)
        self._ensure_open(ticket)
        technician = self._users.require(technician_id)
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
        self._repository.update(ticket)
        self._publish(
            TicketAssigned(
                ticket_id=ticket.id,
                actor_id=actor.id if actor is not None else technician_id,
                requester_id=ticket.requester_id,
                technician_id=technician_id,
            )
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
        resolved_author_id = self._resolve_user_id(
            author,
            fallback_id=author_id,
            field="author_id",
        )
        # Quien no puede ver el ticket tampoco puede comentarlo (404, no 403).
        author_user = author if isinstance(author, User) else self._users.require(resolved_author_id)
        self._ensure_visible(ticket, author_user)
        self._ensure_open(ticket)
        if body is None:
            raise ValidationError("comment body is required", field="body")
        trimmed_body = body.strip()
        if not trimmed_body:
            raise ValidationError("comment body is required", field="body")

        comment = Comment(
            ticket_id=ticket_id,
            author_id=resolved_author_id,
            body=trimmed_body,
        )
        ticket.comments.append(comment)
        ticket.updated_at = self._now()
        self._record_history(
            ticket=ticket,
            event_type="commented",
            actor_id=resolved_author_id,
            detail="comment added",
        )
        self._repository.update(ticket)
        self._publish(
            TicketCommented(
                ticket_id=ticket.id,
                actor_id=resolved_author_id,
                requester_id=ticket.requester_id,
                comment_id=comment.id,
            )
        )
        return comment

    def add_comment(self, ticket_id: int, author_id: int, body: str) -> Comment:
        return self.comment(ticket_id=ticket_id, author_id=author_id, body=body)

    # 22/10/2026 - Nuevo caso de uso de la semana 13: cambiar la prioridad. La base
    # recalcula due_at con su trigger y update() me devuelve el valor nuevo.
    def change_priority(
        self,
        ticket_id: int,
        new_priority: str,
        actor: User,
    ) -> Ticket:
        if not actor.is_staff:
            raise PermissionDeniedError(
                "Only staff users can change ticket priority",
                actor_id=actor.id,
                ticket_id=ticket_id,
            )
        ticket = self.require(ticket_id)
        self._ensure_open(ticket)
        if new_priority not in PRIORITIES:
            raise ValidationError("priority is invalid", field="priority")

        previous_priority = ticket.priority
        ticket.priority = new_priority
        ticket.updated_at = self._now()
        self._record_history(
            ticket=ticket,
            event_type="priority_changed",
            actor_id=actor.id,
            detail=f"{previous_priority} -> {new_priority}",
        )
        # update() devuelve al ticket el due_at que recalculo el trigger de la base.
        self._repository.update(ticket)
        return ticket

    def change_status(
        self,
        ticket_id: int,
        new_status: TicketStatus | str,
        actor: User,
    ) -> Ticket:
        if not actor.is_staff:
            raise PermissionDeniedError(
                "Only staff users can change ticket status",
                actor_id=actor.id,
                ticket_id=ticket_id,
            )
        ticket = self.require(ticket_id)

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
        self._repository.update(ticket)
        self._publish(
            TicketStatusChanged(
                ticket_id=ticket.id,
                actor_id=actor.id,
                requester_id=ticket.requester_id,
                new_status=ticket.status,
            )
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
        self._repository.update(ticket)
        self._publish(
            TicketCancelled(
                ticket_id=ticket.id,
                actor_id=resolved_requester_id,
                requester_id=ticket.requester_id,
            )
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
            ticket_id=ticket.id,
            actor_id=actor_id,
            event_type=event_type,
            detail=detail,
        )
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

    def _ensure_visible(self, ticket: Ticket, user: User) -> None:
        if not user.is_staff and ticket.requester_id != user.id:
            raise TicketNotFoundError(ticket.id)

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

    def _publish(self, event: TicketEvent) -> None:
        """22/10/2026 - Unico punto por donde sale un evento hacia los suscriptores."""
        self._events.publish(event)

    def _now(self) -> datetime:
        return now()
