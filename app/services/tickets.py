from datetime import datetime

from app.models.assignments import Assignment
from app.models.comments import Comment
from app.models.entities import Ticket
from app.models.enums import TicketStatus


class TicketService:
    # initialize the ticket service with an empty list of tickets and a next_id counter
    def __init__(self) -> None:
        self._tickets: list[Ticket] = []
        self._assignments: list[Assignment] = []
        self._comments: list[Comment] = []
        self.next_id = 1
        self.next_comment_id = 1

    # create a new ticket
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
            status=TicketStatus(status),
        )
        self._tickets.append(ticket)
        self.next_id += 1
        return ticket

    # list all tickets
    def list(self) -> list[Ticket]:
        return self._tickets

    def find_by_id(self, ticket_id: int) -> Ticket | None:
        for ticket in self._tickets:
            if ticket.id == ticket_id:
                return ticket
        return None

    def assign_technician(self, ticket_id: int, technician_id: int) -> Assignment:
        ticket = self._require_ticket(ticket_id)
        ticket.assignee_id = technician_id
        ticket.updated_at = datetime.now().astimezone()

        assignment = Assignment(
            ticket_id=ticket_id,
            technician_id=technician_id,
        )
        self._assignments.append(assignment)
        return assignment

    def add_comment(self, ticket_id: int, author_id: int, body: str) -> Comment:
        ticket = self._require_ticket(ticket_id)
        comment = Comment(
            id=self.next_comment_id,
            ticket_id=ticket_id,
            author_id=author_id,
            body=body,
        )
        self.next_comment_id += 1
        self._comments.append(comment)
        ticket.comments.append(comment)
        ticket.updated_at = datetime.now().astimezone()
        return comment

    def list_by_technician(self, technician_id: int) -> list[Ticket]:
         return [
             ticket
             for ticket in self._tickets
             if ticket.assignee_id == technician_id
        ]
        
    def list_by_category(self, category: str) -> list[Ticket]:
        return [
            ticket
            for ticket in self._tickets
            if ticket.category == category
        ]
        
    def list_by_status(self, status: str | TicketStatus) -> list[Ticket]:
        if isinstance(status, str):
            status = TicketStatus(status.lower())
            
        return [
            ticket
            for ticket in self._tickets
            if ticket.status == status 
        ]
        
    def _require_ticket(self, ticket_id: int) -> Ticket:
        ticket = self.find_by_id(ticket_id)
        if ticket is None:
            raise ValueError(f"Ticket {ticket_id} was not found")
        return ticket
