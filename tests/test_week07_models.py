import pytest

from app.models import entities
from app.models.enums import Role, TicketStatus
from app.services.tickets import TicketService


def create_ticket(service: TicketService, **overrides):
    data = {
        "title": "No puedo ingresar al campus virtual",
        "description": "El usuario recibe error de credenciales",
        "category": "Software",
        "priority": "High",
        "requester_id": 1,
    }
    data.update(overrides)
    return service.create(**data)


def test_create_ticket_assigns_sequential_ids_and_open_status():
    service = TicketService()

    first_ticket = create_ticket(service)
    second_ticket = create_ticket(service, title="No imprime")

    assert first_ticket.id == 1
    assert second_ticket.id == 2
    assert first_ticket.status is TicketStatus.OPEN
    assert first_ticket.status == "open"


def test_ticket_list_returns_a_copy():
    service = TicketService()
    ticket = create_ticket(service)

    listed_tickets = service.list()
    listed_tickets.clear()

    assert service.list() == [ticket]


def test_ticket_service_finds_ticket_by_id():
    service = TicketService()
    ticket = create_ticket(service)

    assert service.by_id(ticket.id) is ticket
    assert service.by_id(999) is None


def test_ticket_service_lists_tickets_by_status():
    service = TicketService()
    open_ticket = create_ticket(service)
    resolved_ticket = create_ticket(
        service,
        title="La impresora vuelve a funcionar",
        status=TicketStatus.RESOLVED,
    )

    assert service.list_by_status(TicketStatus.OPEN) == [open_ticket]
    assert service.list_by_status(TicketStatus.RESOLVED) == [resolved_ticket]


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
def test_ticket_service_rejects_invalid_ticket_data(field, value, match):
    service = TicketService()

    with pytest.raises(ValueError, match=match):
        create_ticket(service, **{field: value})


def test_ticket_service_stores_trimmed_title():
    service = TicketService()

    ticket = create_ticket(service, title="  No imprime  ")

    assert ticket.title == "No imprime"


def test_role_behaves_like_a_string():
    assert Role.REQUESTER == "requester"
    assert str(Role.TECHNICIAN) == "technician"


def test_ticket_knows_if_it_is_open():
    service = TicketService()

    open_ticket = create_ticket(service)
    in_progress_ticket = create_ticket(
        service,
        title="Un técnico revisa la impresora",
        status=TicketStatus.IN_PROGRESS,
    )
    resolved_ticket = create_ticket(
        service,
        title="La impresora vuelve a funcionar",
        status=TicketStatus.RESOLVED,
    )
    closed_ticket = create_ticket(
        service,
        title="El caso fue cerrado",
        status=TicketStatus.CLOSED,
    )
    cancelled_ticket = create_ticket(
        service,
        title="El usuario canceló el caso",
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
