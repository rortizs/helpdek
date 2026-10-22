"""22/10/2026 - Arma los servicios sobre UNA sola sesion (semanas 13 y 15).

Es el unico lugar donde conecto servicios con repositorios SQLAlchemy y donde
decido quien escucha los eventos de un ticket; si manana cambia la persistencia
o hay un suscriptor nuevo, cambia esta funcion y no las reglas de negocio.
"""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.repositories.sqlalchemy import (
    SqlAlchemyNotificationRepository,
    SqlAlchemyTicketRepository,
    SqlAlchemyUserRepository,
)
from app.services.audit import AuditLogSubscriber
from app.services.events import TicketEventSubscriber
from app.services.notifications import DatabaseNotifier, Notifier
from app.services.tickets import TicketService
from app.services.users import UserService


def build_services(
    session: Session,
    notifier: Notifier | None = None,
    subscribers: Iterable[TicketEventSubscriber] | None = None,
) -> tuple[UserService, TicketService]:
    """22/10/2026 - Todos los repositorios comparten `session`: usuarios, tickets y avisos
    se confirman (o se revierten) juntos, y se ven entre si antes del commit.

    Por defecto el ticket tiene dos suscriptores: el notificador que guarda los avisos
    en la base (dentro de la misma sesion) y la auditoria por `logging`. Quien llama
    puede reemplazar los suscriptores (por ejemplo en una prueba)."""
    users = UserService(SqlAlchemyUserRepository(session))
    notifier = notifier or DatabaseNotifier(SqlAlchemyNotificationRepository(session))
    if subscribers is None:
        subscribers = [AuditLogSubscriber()]
    tickets = TicketService(
        SqlAlchemyTicketRepository(session), users, notifier=notifier, subscribers=subscribers
    )
    return users, tickets
