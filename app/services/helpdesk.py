"""22/10/2026 - HelpDeskFacade: la puerta unica a los casos de uso (semana 15, patron Facade).

PROBLEMA que tenia antes: cada ruta recibia una bolsa `Services` con cuatro
servicios (usuarios, tickets, avisos, autenticacion) y decidia por su cuenta a
cual llamar y en que orden. El login, por ejemplo, eran DOS llamadas
(authenticate + issue_token) escritas dentro de la ruta; y para probar una ruta
hacia falta armar los cuatro servicios.

SOLUCION: esta fachada expone los casos de uso con nombres del negocio (abrir un
ticket, asignar, comentar, ver mis avisos...). Las rutas dependen de UN objeto y
no saben cuantos servicios hay detras. Si un caso de uso necesita coordinar dos
servicios, esa coordinacion vive aqui y no se copia en cada ruta.

LIMITE honesto: casi todos los metodos de abajo solo reenvian a un servicio. La
fachada NO agrega reglas de negocio (esas siguen en los servicios) y no sustituye
a los servicios: los usa. Si algun dia un metodo se limita a reenviar y nadie
necesita ese nombre, sobra.
"""

from __future__ import annotations

from app.core.security import decode_access_token
from app.domain.errors import AuthenticationError
from app.models.comments import Comment
from app.models.entities import Ticket, User
from app.models.enums import Role, TicketStatus
from app.repositories.base import TicketPage
from app.services.auth import AuthService
from app.services.notifications import Notification, NotificationService
from app.services.tickets import TicketService
from app.services.users import UserService


class HelpDeskFacade:
    """22/10/2026 - Casos de uso de HelpDesk EDU para la capa HTTP (y para cualquier otro cliente)."""

    def __init__(
        self,
        users: UserService,
        tickets: TicketService,
        notifications: NotificationService,
        auth: AuthService,
    ) -> None:
        self._users = users
        self._tickets = tickets
        self._notifications = notifications
        self._auth = auth

    # --- identidad ------------------------------------------------------------------

    def login(self, email: str, password: str) -> tuple[str, int]:
        """22/10/2026 - Correo + contrasena -> (token, segundos de vida). Dos pasos, una sola llamada."""
        user = self._auth.authenticate(email, password)
        return self._auth.issue_token(user)

    def user_from_token(self, token: str) -> User:
        """22/10/2026 - Quien es el dueno del token. Un usuario borrado se trata como token invalido."""
        user = self._users.by_id(decode_access_token(token))
        if user is None:
            raise AuthenticationError("invalid or expired token")  # mismo mensaje que un token malo
        return user

    # --- usuarios -------------------------------------------------------------------

    def list_users(self, actor: User, role: Role | None = None) -> list[User]:
        return self._users.list_for(actor, role=role)

    def get_user(self, actor: User, user_id: int) -> User:
        return self._users.require_for(actor, user_id)

    def create_user(
        self,
        actor: User,
        *,
        email: str,
        name: str,
        role: Role,
        password: str | None,
    ) -> User:
        return self._users.register_by(actor, email=email, name=name, role=role, password=password)

    # --- tickets --------------------------------------------------------------------

    def open_ticket(
        self,
        requester: User,
        *,
        title: str,
        description: str,
        category: str,
        priority: str,
    ) -> Ticket:
        """22/10/2026 - Abre un ticket a nombre de quien hace la peticion."""
        return self._tickets.create(
            title=title,
            description=description,
            category=category,
            priority=priority,
            requester=requester,
        )

    def list_tickets(self, actor: User, **filters) -> TicketPage:
        """22/10/2026 - Filtros y pagina tal como los acepta TicketService.list_for."""
        return self._tickets.list_for(actor, **filters)

    def get_ticket(self, actor: User, ticket_id: int) -> Ticket:
        return self._tickets.require_for(actor, ticket_id)

    def list_comments(self, actor: User, ticket_id: int) -> list[Comment]:
        return self._tickets.require_for(actor, ticket_id).comments

    def comment(self, author: User, ticket_id: int, body: str) -> Comment:
        return self._tickets.comment(ticket_id, author=author, body=body)

    def assign(self, actor: User, ticket_id: int, technician_id: int) -> Ticket:
        return self._tickets.assign(ticket_id, technician_id, actor=actor)

    def change_status(self, actor: User, ticket_id: int, status: TicketStatus) -> Ticket:
        return self._tickets.change_status(ticket_id, status, actor=actor)

    def change_priority(self, actor: User, ticket_id: int, priority: str) -> Ticket:
        return self._tickets.change_priority(ticket_id, priority, actor=actor)

    def cancel(self, actor: User, ticket_id: int) -> Ticket:
        return self._tickets.cancel(ticket_id, actor=actor)

    # --- avisos ---------------------------------------------------------------------

    def my_notifications(self, user: User) -> list[Notification]:
        """22/10/2026 - Solo los avisos sin leer de quien pregunta, nunca los de otra persona."""
        return self._notifications.unread_for(user.id)

    def mark_notifications_read(self, user: User) -> int:
        return self._notifications.mark_all_read(user.id)
