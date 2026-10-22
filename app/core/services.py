"""22/10/2026 - Arma los servicios sobre UNA sola sesion (semana 13).

Es el unico lugar donde conecto servicios con repositorios SQLAlchemy; si manana
cambia la persistencia, cambia esta funcion y no las reglas de negocio.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.sqlalchemy import (
    SqlAlchemyNotificationRepository,
    SqlAlchemyTicketRepository,
    SqlAlchemyUserRepository,
)
from app.services.notifications import DatabaseNotifier, Notifier
from app.services.tickets import TicketService
from app.services.users import UserService


def build_services(
    session: Session,
    notifier: Notifier | None = None,
) -> tuple[UserService, TicketService]:
    """22/10/2026 - Todos los repositorios comparten `session`: usuarios, tickets y avisos
    se confirman (o se revierten) juntos, y se ven entre si antes del commit."""
    users = UserService(SqlAlchemyUserRepository(session))
    notifier = notifier or DatabaseNotifier(SqlAlchemyNotificationRepository(session))
    tickets = TicketService(SqlAlchemyTicketRepository(session), users, notifier=notifier)
    return users, tickets
