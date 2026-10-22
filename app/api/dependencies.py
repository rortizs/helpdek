"""22/10/2026 - Dependencias de FastAPI: lo que cada peticion recibe ya armado (semana 14).

Cada peticion obtiene UNA sesion (`get_db`) y, sobre ella, los servicios
(`get_services`). Si la ruta termina bien se hace commit; si lanza un error,
rollback. Las rutas no abren sesiones ni conocen SQLAlchemy.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, NamedTuple

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import decode_access_token
from app.core.services import build_services
from app.domain.errors import AuthenticationError
from app.models.entities import User
from app.repositories.sqlalchemy import SqlAlchemyNotificationRepository, SqlAlchemyUserRepository
from app.services.auth import AuthService
from app.services.notifications import NotificationService
from app.services.tickets import TicketService
from app.services.users import UserService


# 22/10/2026 - Agrupo los servicios de una peticion en una sola tupla con nombre, asi
# las rutas piden UNA dependencia y no cuatro.
class Services(NamedTuple):
    users: UserService
    tickets: TicketService
    notifications: NotificationService
    auth: AuthService


def get_db() -> Iterator[Session]:
    """22/10/2026 - La unidad de trabajo de la semana 13, entregada por peticion."""
    yield from get_session()


# scope="function": el commit/rollback ocurre al terminar la RUTA, antes de enviar
# la respuesta. Con el scope por defecto correria despues de responder y un COMMIT
# fallido no podria cambiar un 201 que el cliente ya recibio.
DbSession = Annotated[Session, Depends(get_db, scope="function")]


def get_services(db: DbSession) -> Services:
    """22/10/2026 - Armo los servicios sobre la sesion de ESTA peticion: asi todo se confirma o se revierte junto."""
    users, tickets = build_services(db)
    notifications = NotificationService(SqlAlchemyNotificationRepository(db))
    auth = AuthService(SqlAlchemyUserRepository(db))
    return Services(users=users, tickets=tickets, notifications=notifications, auth=auth)


ServicesDep = Annotated[Services, Depends(get_services)]


# auto_error=False: el error lo lanzamos nosotros para que tenga el mismo formato
# JSON que los demas (error / message / details). Tambien publica el esquema
# "Bearer" en /docs, donde aparece el boton Authorize.
bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    services: ServicesDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    """22/10/2026 - Quien hace la peticion, segun el token `Authorization: Bearer ...`.

    Reemplaza a la identidad temporal `X-User-Id` de la semana 14: ahora el
    token esta firmado, vence, y no se puede fabricar sin SECRET_KEY. Las rutas
    no cambiaron: siguen recibiendo un `User` como `actor`.
    """
    if credentials is None:
        raise AuthenticationError("bearer token required")
    user = services.users.by_id(decode_access_token(credentials.credentials))
    if user is None:
        raise AuthenticationError("invalid or expired token")  # mismo mensaje que un token malo
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
