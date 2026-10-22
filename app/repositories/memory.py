"""22/10/2026 - Repositorios en memoria: el doble de pruebas que imita a PostgreSQL.

Los uso para probar reglas de negocio rapido y sin base de datos. Respetan el
mismo contrato que los repositorios SQLAlchemy, incluidos los ids asignados por
el almacenamiento (un contador por tabla, como un SERIAL).
"""

from app.models.entities import Ticket, User
from app.models.enums import TicketStatus
from app.repositories.base import TicketRepository, UserRepository


class InMemoryTicketRepository(TicketRepository):
    """22/10/2026 - Imita a PostgreSQL: cada tabla tiene su propio contador (como un SERIAL)."""

    def __init__(self) -> None:
        self._items: dict[int, Ticket] = {}
        self._next_ticket_id = 1
        self._next_comment_id = 1
        self._next_event_id = 1

    def add(self, ticket: Ticket) -> Ticket:
        ticket.id = self._next_ticket_id
        self._next_ticket_id += 1
        self._items[ticket.id] = ticket
        return ticket

    def update(self, ticket: Ticket) -> Ticket:
        # Solo los objetos nuevos (id None) reciben llave, igual que un INSERT.
        for comment in ticket.comments:
            if comment.id is None:
                comment.id = self._next_comment_id
                self._next_comment_id += 1
        for event in ticket.history:
            if event.id is None:
                event.id = self._next_event_id
                self._next_event_id += 1
        self._items[ticket.id] = ticket
        return ticket

    def by_id(self, ticket_id: int) -> Ticket | None:
        return self._items.get(ticket_id)

    def list(
        self,
        *,
        status: TicketStatus | str | None = None,
        category: str | None = None,
        priority: str | None = None,
        assignee_id: int | None = None,
        requester_id: int | None = None,
    ) -> list[Ticket]:
        tickets = list(self._items.values())
        if status is not None:
            ticket_status = TicketStatus(status)
            tickets = [ticket for ticket in tickets if ticket.status is ticket_status]
        if category is not None:
            tickets = [ticket for ticket in tickets if ticket.category == category]
        if priority is not None:
            tickets = [ticket for ticket in tickets if ticket.priority == priority]
        if assignee_id is not None:
            tickets = [ticket for ticket in tickets if ticket.assignee_id == assignee_id]
        if requester_id is not None:
            tickets = [ticket for ticket in tickets if ticket.requester_id == requester_id]
        return list(tickets)

    def by_category(self, category: str) -> list[Ticket]:
        return self.list(category=category)

    def count_by_status(self) -> dict[str, int]:
        """22/10/2026 - Cuento en Python lo que PostgreSQL cuenta con un GROUP BY."""
        counts: dict[str, int] = {}
        for ticket in self._items.values():
            counts[ticket.status.value] = counts.get(ticket.status.value, 0) + 1
        return counts

    # 22/10/2026 - En memoria no hay transaccion: commit y rollback no hacen nada.
    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass


class InMemoryUserRepository(UserRepository):
    """22/10/2026 - Usuarios en un diccionario, con su propio contador de ids."""

    def __init__(self) -> None:
        self._items: dict[int, User] = {}
        self._next_id = 1

    def add(self, user: User) -> User:
        user.id = self._next_id
        self._next_id += 1
        self._items[user.id] = user
        return user

    def by_id(self, user_id: int) -> User | None:
        return self._items.get(user_id)

    def by_email(self, email: str) -> User | None:
        normalized_email = email.strip().lower()
        return next(
            (user for user in self._items.values() if user.email == normalized_email),
            None,
        )

    def all(self) -> list[User]:
        return list(self._items.values())
