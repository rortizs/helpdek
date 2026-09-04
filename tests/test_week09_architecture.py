import pytest

from app.domain.errors import (
    InvalidStatusTransitionError,
    PermissionDeniedError,
    TicketNotFoundError,
)
from app.domain.workflow import assert_transition, can_transition
from app.models.enums import Role, TicketStatus
from app.repositories.base import TicketRepository, UserRepository
from app.repositories.memory import InMemoryTicketRepository
from app.services.notifications import NullNotifier, RecordingNotifier
from app.services.tickets import TicketService


def create_ticket(service, requester=None, requester_id=1, **overrides):
    data: dict[str, object] = {
        "title": "No puedo conectarme al WiFi",
        "description": "La red institucional no autentica al usuario",
        "category": "Network",
        "priority": "High",
    }
    if requester is not None:
        data["requester"] = requester
    else:
        data["requester_id"] = requester_id
    data.update(overrides)
    return service.create(**data)


def test_workflow_allows_expected_transitions_and_rejects_invalid_shortcuts():
    assert can_transition(TicketStatus.OPEN, TicketStatus.IN_PROGRESS) is True
    assert can_transition("in_progress", "resolved") is True
    assert can_transition(TicketStatus.IN_PROGRESS, TicketStatus.OPEN) is True
    assert can_transition(TicketStatus.RESOLVED, TicketStatus.CLOSED) is True
    assert can_transition(TicketStatus.OPEN, TicketStatus.CLOSED) is False
    assert can_transition(TicketStatus.CANCELLED, TicketStatus.OPEN) is False


def test_workflow_error_exposes_lowercase_transition_properties():
    with pytest.raises(InvalidStatusTransitionError) as error:
        assert_transition(TicketStatus.OPEN, TicketStatus.CLOSED)

    assert error.value.code == "invalid_status_transition"
    assert error.value.properties == {
        "from_status": "open",
        "to_status": "closed",
    }


def test_missing_ticket_raises_domain_error_with_ticket_id(world):
    with pytest.raises(TicketNotFoundError) as error:
        world.tickets.require(404)

    assert error.value.code == "ticket_not_found"
    assert error.value.properties["ticket_id"] == 404


def test_requester_can_only_cancel_own_ticket(world):
    own_ticket = create_ticket(world.tickets, requester=world.requester)
    other_requester = world.users.register(
        "luis@school.edu",
        "Luis Solicitante",
        role=Role.REQUESTER,
    )
    other_ticket = create_ticket(world.tickets, requester=world.requester, title="VPN caída")

    cancelled = world.tickets.cancel(own_ticket.id, actor=world.requester)

    assert cancelled.status is TicketStatus.CANCELLED
    assert cancelled.history[-1].event_type == "cancelled"
    assert cancelled.history[-1].detail == "cancelled"
    with pytest.raises(PermissionDeniedError):
        world.tickets.cancel(other_ticket.id, actor=other_requester)
    assert other_ticket.status is TicketStatus.OPEN


def test_notifier_polymorphism_records_or_discards_notifications(world, users):
    ticket = create_ticket(world.tickets, requester=world.requester)

    world.tickets.assign(ticket.id, technician_id=world.technician.id)

    notification = world.notifier.sent[-1]
    assert notification.user_id == world.technician.id
    assert notification.title == "ticket_assigned"
    assert notification.message == f"Ticket #{ticket.id} was assigned to you"
    assert world.notifier.notifications == world.notifier.sent

    null_service = TicketService(InMemoryTicketRepository(), users, notifier=NullNotifier())
    null_ticket = create_ticket(null_service, requester=world.requester, title="Sin sonido")

    assert null_service.assign(null_ticket.id, technician_id=world.technician.id) is null_ticket


def test_abstract_repositories_cannot_be_instantiated():
    with pytest.raises(TypeError):
        TicketRepository()  # type: ignore[abstract]
    with pytest.raises(TypeError):
        UserRepository()  # type: ignore[abstract]


class AlternateTicketRepository(TicketRepository):
    def __init__(self):
        self._tickets = {}
        self._next_id = 1

    def add(self, ticket):
        self._tickets[ticket.id] = ticket
        self._next_id = max(self._next_id, ticket.id + 1)
        return ticket

    def by_id(self, ticket_id):
        return self._tickets.get(ticket_id)

    def list(self, status=None, assignee_id=None, requester_id=None):
        tickets = list(self._tickets.values())
        if status is not None:
            status = TicketStatus(status)
            tickets = [ticket for ticket in tickets if ticket.status is status]
        if assignee_id is not None:
            tickets = [ticket for ticket in tickets if ticket.assignee_id == assignee_id]
        if requester_id is not None:
            tickets = [ticket for ticket in tickets if ticket.requester_id == requester_id]
        return list(tickets)

    def next_id(self):
        ticket_id = self._next_id
        self._next_id += 1
        return ticket_id


def test_ticket_service_accepts_alternate_repository_implementation(users):
    notifier = RecordingNotifier()
    service = TicketService(AlternateTicketRepository(), users, notifier=notifier)

    ticket = create_ticket(service, requester_id=users.by_email("sofia@school.edu").id)
    service.assign(ticket.id, technician_id=users.by_email("tomas@school.edu").id)

    assert service.require(ticket.id) is ticket
    assert service.assigned_to(users.by_email("tomas@school.edu").id) == [ticket]
    assert notifier.sent[-1].user_id == users.by_email("tomas@school.edu").id
