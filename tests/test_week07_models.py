from app.services.tickets import TicketService

def test_create_ticket_in_memory():
    service = TicketService()
    
    ticket = service.create(
      title="No puedo ingresar al campus virtual",
      description="El usuario recibe error de credenciales",
      category="Software",
      priority="High",
      requester_id=1,
    )
    
    assert ticket.id == 1
    assert ticket.status == "open"
    assert len(service.list()) == 1