from app.models.entities import Ticket

class TicketService:
    # initialize the ticket service with an empty list of tickets and a next_id counter
    def __init__(self) -> None:
        self._tickets: list[Ticket] = []
        self.next_id = 1
    
    #create a new ticket
    def create(
      self,
      title: str,
      description: str,
      category: str,
      priority: str,
      requester_id: int,
      status: str = "open",
      ) -> Ticket:
        ticket = Ticket(
          id=self.next_id,
          title=title,
          description=description,
          category=category,
          priority=priority,
          requester_id=requester_id,
          status=status,
        )
        self._tickets.append(ticket)
        self.next_id += 1
        return ticket
      
      #list all tickets
    def list(self) -> list[Ticket]:
        return self._tickets
