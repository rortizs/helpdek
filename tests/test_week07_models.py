import pytest

from app.domain.errors import ValidationError
from app.models import entities
from app.models.enums import Role, TicketStatus


def create_ticket(service, requester_id=1, **overrides):
    data = {
        "title": "No puedo ingresar al campus virtual",
        "description": "El usuario recibe error de credenciales",
        "category": "Software",
        "priority": "High",
        "requester_id": requester_id,
    }
    data.update(overrides)
    return service.create(**data)


def test_create_ticket_assigns_sequential_ids_and_open_status(tickets, world):
    first_ticket = create_ticket(tickets, requester_id=world.requester.id)
    second_ticket = create_ticket(
        tickets,
        requester_id=world.requester.id,
        title="No imprime",
    )

    assert first_ticket.id == 1
    assert second_ticket.id == 2
    assert first_ticket.status is TicketStatus.OPEN
    assert first_ticket.status == "open"


def test_ticket_list_returns_a_copy(tickets, world):
    ticket = create_ticket(tickets, requester_id=world.requester.id)

    listed_tickets = tickets.list()
    listed_tickets.clear()

    assert tickets.list() == [ticket]


def test_ticket_service_finds_ticket_by_id(tickets, world):
    ticket = create_ticket(tickets, requester_id=world.requester.id)

    assert tickets.by_id(ticket.id) is ticket
    assert tickets.by_id(999) is None
    assert tickets.require(ticket.id) is ticket


def test_ticket_service_lists_tickets_by_status(tickets, world):
    open_ticket = create_ticket(tickets, requester_id=world.requester.id)
    resolved_ticket = create_ticket(
        tickets,
        requester_id=world.requester.id,
        title="La impresora vuelve a funcionar",
        status=TicketStatus.RESOLVED,
    )

    assert tickets.list(status=TicketStatus.OPEN) == [open_ticket]
    assert tickets.list(status=TicketStatus.RESOLVED) == [resolved_ticket]
    assert tickets.list_by_status(TicketStatus.RESOLVED) == [resolved_ticket]


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("title", "", "title"),
        ("title", "No", "title"),
        ("title", "  No  ", "title"),
        ("category", "Unknown", "category"),
        ("priority", "Urgent", "priority"),
    ],
)
def test_ticket_service_rejects_invalid_ticket_data(tickets, world, field, value, match):
    with pytest.raises(ValidationError, match=match):
        create_ticket(tickets, requester_id=world.requester.id, **{field: value})


def test_ticket_service_stores_trimmed_title(tickets, world):
    ticket = create_ticket(tickets, requester_id=world.requester.id, title="  No imprime  ")

    assert ticket.title == "No imprime"


def test_role_behaves_like_a_string():
    assert Role.REQUESTER == "requester"
    assert str(Role.TECHNICIAN) == "technician"


def test_ticket_knows_if_it_is_open():
    open_ticket = entities.Ticket(
        id=1,
        title="Abierto",
        description="Caso abierto",
        category="Software",
        priority="Low",
        requester_id=1,
        status=TicketStatus.OPEN,
    )
    in_progress_ticket = entities.Ticket(
        id=2,
        title="En progreso",
        description="Caso en progreso",
        category="Software",
        priority="Low",
        requester_id=1,
        status=TicketStatus.IN_PROGRESS,
    )
    resolved_ticket = entities.Ticket(
        id=3,
        title="Resuelto",
        description="Caso resuelto",
        category="Software",
        priority="Low",
        requester_id=1,
        status=TicketStatus.RESOLVED,
    )
    closed_ticket = entities.Ticket(
        id=4,
        title="Cerrado",
        description="Caso cerrado",
        category="Software",
        priority="Low",
        requester_id=1,
        status=TicketStatus.CLOSED,
    )
    cancelled_ticket = entities.Ticket(
        id=5,
        title="Cancelado",
        description="Caso cancelado",
        category="Software",
        priority="Low",
        requester_id=1,
        status=TicketStatus.CANCELLED,
    )

    assert open_ticket.is_open is True
    assert in_progress_ticket.is_open is True
    assert resolved_ticket.is_open is True
    assert closed_ticket.is_open is False
    assert cancelled_ticket.is_open is False


def test_user_defaults_to_requester_role():
    assert hasattr(entities, "User")

    user = entities.User(id=1, name="Ada Lovelace", email="ada@example.com")

    assert user.role is Role.REQUESTER
    assert user.role == "requester"
