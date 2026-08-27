from app.services.tickets import TicketService


def create_sample_ticket(service: TicketService):
    return service.create(
        title="No puedo imprimir",
        description="La impresora no responde en laboratorio",
        category="Hardware",
        priority="Medium",
        requester_id=1,
    )


def test_category_model_has_identity_and_name():
    from app.models.categories import Category

    category = Category(id=1, name="Hardware")

    assert category.id == 1
    assert category.name == "Hardware"


def test_assign_technician_updates_ticket_and_returns_assignment():
    service = TicketService()
    ticket = create_sample_ticket(service)

    assignment = service.assign_technician(ticket_id=ticket.id, technician_id=2)

    assert ticket.assignee_id == 2
    assert assignment.ticket_id == ticket.id
    assert assignment.technician_id == 2


def test_add_comment_links_comment_to_ticket():
    service = TicketService()
    ticket = create_sample_ticket(service)

    comment = service.add_comment(
        ticket_id=ticket.id,
        author_id=2,
        body="Se revisa el equipo durante el recreo.",
    )

    assert comment.ticket_id == ticket.id
    assert comment.author_id == 2
    assert comment.body == "Se revisa el equipo durante el recreo."
    assert ticket.comments == [comment]


def test_assign_technician_rejects_unknown_ticket():
    service = TicketService()

    try:
        service.assign_technician(ticket_id=99, technician_id=2)
    except ValueError as error:
        assert "Ticket 99" in str(error)
    else:
        raise AssertionError("Expected unknown ticket assignment to fail")
