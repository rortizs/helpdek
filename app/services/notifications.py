"""22/10/2026 - Avisos del sistema (notifier) y su version persistente.

TicketService solo conoce la interfaz Notifier; aqui viven las implementaciones
(nula, consola, grabadora para pruebas y base de datos). Los avisos viejos de las
semanas 7-9 siguen funcionando porque los campos nuevos son opcionales.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from app.domain.events import (
    TicketAssigned,
    TicketCancelled,
    TicketCommented,
    TicketCreated,
    TicketEvent,
    TicketStatusChanged,
)


@dataclass(frozen=True)
class Notification:
    user_id: int
    title: str
    message: str
    # Campos nuevos (semana 13), todos opcionales para no romper el codigo anterior.
    ticket_id: int | None = None
    type: str | None = None
    id: int | None = None
    read_at: datetime | None = None
    created_at: datetime | None = None

    @property
    def to_user_id(self) -> int:
        return self.user_id


class Notifier(ABC):
    @abstractmethod
    def notify(
        self,
        user_id: int,
        title: str,
        message: str,
        ticket_id: int | None = None,
        type: str | None = None,
    ) -> None:
        raise NotImplementedError


class NullNotifier(Notifier):
    def notify(
        self,
        user_id: int,
        title: str,
        message: str,
        ticket_id: int | None = None,
        type: str | None = None,
    ) -> None:
        return None


class ConsoleNotifier(Notifier):
    def notify(
        self,
        user_id: int,
        title: str,
        message: str,
        ticket_id: int | None = None,
        type: str | None = None,
    ) -> None:
        print(f"[{title}] user={user_id}: {message}")


class RecordingNotifier(Notifier):
    def __init__(self) -> None:
        self.sent: list[Notification] = []

    @property
    def notifications(self) -> list[Notification]:
        return list(self.sent)

    def notify(
        self,
        user_id: int,
        title: str,
        message: str,
        ticket_id: int | None = None,
        type: str | None = None,
    ) -> None:
        self.sent.append(
            Notification(
                user_id=user_id,
                title=title,
                message=message,
                ticket_id=ticket_id,
                type=type,
            )
        )


class NotificationRepository(ABC):
    """22/10/2026 - Contrato de almacenamiento de avisos (lo implementa SQLAlchemy)."""

    @abstractmethod
    def add(self, notification: Notification) -> Notification:
        ...

    @abstractmethod
    def unread_for(self, user_id: int) -> list[Notification]:
        ...

    @abstractmethod
    def mark_all_read(self, user_id: int) -> int:
        ...


class NotificationService:
    """22/10/2026 - Los avisos de una persona: lo que tiene sin leer y marcarlos como leidos."""

    def __init__(self, repository: NotificationRepository) -> None:
        self._repository = repository

    def unread_for(self, user_id: int) -> list[Notification]:
        return self._repository.unread_for(user_id)

    def mark_all_read(self, user_id: int) -> int:
        return self._repository.mark_all_read(user_id)


# El servicio sigue llamando a notify() con un codigo ("ticket_assigned") como
# `title`; al guardar, ese codigo pasa a la columna `type` y el titulo que ve
# el usuario es un texto legible.
READABLE_TITLES = {
    "ticket_created": "Ticket creado",
    "ticket_assigned": "Ticket asignado",
    "ticket_commented": "Nuevo comentario",
    "ticket_status_changed": "Cambio de estado",
    "ticket_cancelled": "Ticket cancelado",
}


class DatabaseNotifier(Notifier):
    """22/10/2026 - Guarda los avisos en la base, en la MISMA sesion de la operacion.

    Si la operacion falla y se hace rollback, el aviso tampoco queda guardado.
    """

    def __init__(self, repository: NotificationRepository) -> None:
        self._repository = repository

    def notify(
        self,
        user_id: int,
        title: str,
        message: str,
        ticket_id: int | None = None,
        type: str | None = None,
    ) -> None:
        notification_type = type or title
        self._repository.add(
            Notification(
                user_id=user_id,
                title=READABLE_TITLES.get(notification_type, title),
                message=message,
                ticket_id=ticket_id,
                type=notification_type,
            )
        )


# 22/10/2026 - Adaptador entre el Observer y el Notifier de las semanas anteriores.
# Traduce cada evento de dominio a la MISMA llamada notify(...) de siempre (mismos
# codigos y mismos textos), asi los notificadores y las pruebas viejas no cambian.
# La regla "no avisar al solicitante de su propio comentario" vive aqui, porque es
# una regla de avisos y no del ticket.
class NotifierSubscriber:
    """22/10/2026 - Suscriptor que convierte eventos de ticket en avisos via un Notifier."""

    def __init__(self, notifier: Notifier) -> None:
        self._notifier = notifier

    def __call__(self, event: TicketEvent) -> None:
        if isinstance(event, TicketCreated):
            self._send(event.requester_id, event, f"Ticket #{event.ticket_id} was created")
        elif isinstance(event, TicketAssigned):
            self._send(event.technician_id, event, f"Ticket #{event.ticket_id} was assigned to you")
        elif isinstance(event, TicketCommented):
            if event.actor_id != event.requester_id:
                self._send(event.requester_id, event, f"Ticket #{event.ticket_id} has a new comment")
        elif isinstance(event, TicketStatusChanged):
            self._send(
                event.requester_id,
                event,
                f"Ticket #{event.ticket_id} changed to {event.new_status.value}",
            )
        elif isinstance(event, TicketCancelled):
            self._send(event.requester_id, event, f"Ticket #{event.ticket_id} was cancelled")

    def _send(self, user_id: int, event: TicketEvent, message: str) -> None:
        self._notifier.notify(user_id, event.name, message, ticket_id=event.ticket_id)
