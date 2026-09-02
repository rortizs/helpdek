from abc import ABC, abstractmethod

from app.models.entities import Ticket

class TicketRepository(ABC):
    @abstractmethod
    def add(self, ticket: Ticket) -> Ticket:
        raise NotImplementedError
    
    @abstractmethod
    def list(self) -> list[Ticket]:
        raise NotImplementedError
    
    @abstractmethod
    def by_id(self, ticket_id: int) -> Ticket | None:
        raise NotImplementedError