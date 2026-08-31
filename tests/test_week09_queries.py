from app.services.tickets import TicketService


def create_ticket(service, title, category, requester_id=1):
    return service.create(
        title=title,
        description="Caso de prueba",
        category=category,
        priority="Medium",
        requester_id=requester_id,
    )
    
def test_list_by_technician_returns_only_assigned_tickets():
    service = TicketService()

    first = create_ticket(service, "No imprime", "Hardware")
    second = create_ticket(service, "No ingresa", "Software")

    service.assign_technician(ticket_id=first.id, technician_id=10)
    service.assign_technician(ticket_id=second.id, technician_id=20)

    result = service.list_by_technician(10)

    assert result == [first]
    
def test_list_by_category_returns_only_matching_category():
    service = TicketService()

    hardware = create_ticket(service, "No imprime", "Hardware")
    create_ticket(service, "No ingresa", "Software")

    result = service.list_by_category("Hardware")

    assert result == [hardware]
    
def test_list_by_status_returns_only_matching_status():
    service = TicketService()

    open_ticket = create_ticket(service, "Caso abierto", "General")

    result = service.list_by_status("open")

    assert open_ticket in result