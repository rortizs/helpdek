"""22/10/2026 - Avisos del sistema (notifier) y su version persistente.

TicketService solo conoce la interfaz Notifier; aqui viven las implementaciones
(nula, consola, grabadora para pruebas y base de datos). Los avisos viejos de las
semanas 7-9 siguen funcionando porque los campos nuevos son opcionales.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


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
