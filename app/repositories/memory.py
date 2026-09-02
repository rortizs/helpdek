from app.models.entities import Ticket
from app.repositories.base import TicketRepository

class InMemoryTicketRepository(TicketRepository):
    def __init__(self) -> None:
        self._items: list[Ticket] = [] # lista de tickets en memoria inicialmente vacía
    
    def add(self, ticket: Ticket) -> Ticket:
        self._items.append(ticket) # agrega el ticket a la lista de tickets en memoria
        return ticket # devuelve el ticket agregado
      
    def list(self) -> list[Ticket]:
        return self._items # devuelve la lista de tickets en memoria
      
    def by_id(self, ticket_id: int) -> Ticket | None:
        return next((ticket for ticket in self._items if ticket.id == ticket_id), None) # busca un ticket por su id en la lista de tickets en memoria y lo devuelve, o None si no se encuentra