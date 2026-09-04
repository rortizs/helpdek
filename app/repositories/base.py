from abc import ABC, abstractmethod

from app.models.entities import Ticket, User
from app.models.enums import TicketStatus


class TicketRepository(ABC):
    @abstractmethod
    def add(self, ticket: Ticket) -> Ticket:
        ...

    @abstractmethod
    def by_id(self, ticket_id: int) -> Ticket | None:
        ...

    @abstractmethod
    def list(
        self,
        status: TicketStatus | str | None = None,
        assignee_id: int | None = None,
        requester_id: int | None = None,
    ) -> list[Ticket]:
        ...

    @abstractmethod
    def next_id(self) -> int:
        ...


class UserRepository(ABC):
    @abstractmethod
    def add(self, user: User) -> User:
        ...

    @abstractmethod
    def by_id(self, user_id: int) -> User | None:
        ...

    @abstractmethod
    def by_email(self, email: str) -> User | None:
        ...

    @abstractmethod
    def all(self) -> list[User]:
        ...

    @abstractmethod
    def next_id(self) -> int:
        ...
