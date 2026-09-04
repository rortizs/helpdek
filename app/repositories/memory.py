from app.models.entities import Ticket, User
from app.models.enums import TicketStatus
from app.repositories.base import TicketRepository, UserRepository


class InMemoryTicketRepository(TicketRepository):
    def __init__(self) -> None:
        self._items: dict[int, Ticket] = {}
        self._next_id = 1

    def add(self, ticket: Ticket) -> Ticket:
        self._items[ticket.id] = ticket
        self._next_id = max(self._next_id, ticket.id + 1)
        return ticket

    def by_id(self, ticket_id: int) -> Ticket | None:
        return self._items.get(ticket_id)

    def list(
        self,
        status: TicketStatus | str | None = None,
        assignee_id: int | None = None,
        requester_id: int | None = None,
    ) -> list[Ticket]:
        tickets = list(self._items.values())
        if status is not None:
            ticket_status = TicketStatus(status)
            tickets = [ticket for ticket in tickets if ticket.status is ticket_status]
        if assignee_id is not None:
            tickets = [ticket for ticket in tickets if ticket.assignee_id == assignee_id]
        if requester_id is not None:
            tickets = [ticket for ticket in tickets if ticket.requester_id == requester_id]
        return list(tickets)

    def next_id(self) -> int:
        ticket_id = self._next_id
        self._next_id += 1
        return ticket_id


class InMemoryUserRepository(UserRepository):
    def __init__(self) -> None:
        self._items: dict[int, User] = {}
        self._next_id = 1

    def add(self, user: User) -> User:
        self._items[user.id] = user
        self._next_id = max(self._next_id, user.id + 1)
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

    def next_id(self) -> int:
        user_id = self._next_id
        self._next_id += 1
        return user_id
