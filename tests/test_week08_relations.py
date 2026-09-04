import pytest

from app.models.entities import User
from app.models.enums import Role, TicketStatus
from app.services.tickets import TicketService


def user_service_class():
    try:
        from app.services.users import UserService
    except ModuleNotFoundError:
        pytest.fail("app.services.users.UserService is required")
    return UserService


def create_sample_ticket(service: TicketService, **overrides):
    data = {
        "title": "No puedo imprimir",
        "description": "La impresora no responde en laboratorio",
        "category": "Hardware",
        "priority": "Medium",
        "requester_id": 1,
    }
    data.update(overrides)
    return service.create(**data)


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


def test_user_service_creates_users_with_normalized_unique_emails():
    UserService = user_service_class()
    service = UserService()

    first = service.create(
        name="Ana Técnica",
        email="  ANA.TECNICA@School.edu  ",
        role=Role.TECHNICIAN,
    )
    second = service.create(name="Bruno Solicitante", email="bruno@school.edu")

    assert first.id == 1
    assert second.id == 2
    assert first.email == "ana.tecnica@school.edu"
    assert second.role is Role.REQUESTER
    assert service.by_id(first.id) is first
    assert service.by_id(999) is None
    with pytest.raises(ValueError, match="email"):
        service.create(name="Duplicada", email="ana.tecnica@school.edu")


def test_user_service_lists_technicians_and_user_knows_staff_role():
    UserService = user_service_class()
    service = UserService()

    requester = service.create("Sofía", "sofia@school.edu", role=Role.REQUESTER)
    technician = service.create("Tomás", "tomas@school.edu", role=Role.TECHNICIAN)
    supervisor = service.create("Carla", "carla@school.edu", role=Role.SUPERVISOR)

    assert requester.is_staff is False
    assert technician.is_staff is True
    assert supervisor.is_staff is True
    assert service.technicians() == [technician]


def test_assignment_and_comments_record_ticket_history():
    service = TicketService()
    ticket = create_sample_ticket(service)

    service.assign_technician(ticket_id=ticket.id, technician_id=2)
    service.add_comment(
        ticket_id=ticket.id,
        author_id=2,
        body="Se revisa el equipo durante el recreo.",
    )

    assert ticket.is_assigned is True
    assert [event.action for event in ticket.history] == ["assigned", "commented"]
    assert ticket.history[0].actor_id == 2
    assert ticket.history[0].details == {"technician_id": 2}
    assert ticket.history[1].details == {"comment_id": 1}


def test_change_status_requires_staff_actor_and_records_history():
    service = TicketService()
    ticket = create_sample_ticket(service)
    requester = User(id=1, name="Sofía", email="sofia@school.edu", role=Role.REQUESTER)
    technician = User(id=2, name="Tomás", email="tomas@school.edu", role=Role.TECHNICIAN)

    with pytest.raises(PermissionError):
        service.change_status(ticket.id, TicketStatus.IN_PROGRESS, actor=requester)

    updated = service.change_status(ticket.id, "in_progress", actor=technician)

    assert updated is ticket
    assert ticket.status is TicketStatus.IN_PROGRESS
    assert ticket.history[-1].action == "status_changed"
    assert ticket.history[-1].actor_id == technician.id
    assert ticket.history[-1].details == {
        "from_status": "open",
        "to_status": "in_progress",
    }


def test_change_status_refuses_closed_or_cancelled_tickets():
    service = TicketService()
    technician = User(id=2, name="Tomás", email="tomas@school.edu", role=Role.TECHNICIAN)
    closed_ticket = create_sample_ticket(service)
    cancelled_ticket = create_sample_ticket(service, title="Cancelar pedido")

    service.change_status(closed_ticket.id, TicketStatus.CLOSED, actor=technician)
    service.change_status(cancelled_ticket.id, TicketStatus.CANCELLED, actor=technician)

    with pytest.raises(ValueError, match="closed or cancelled"):
        service.change_status(closed_ticket.id, TicketStatus.OPEN, actor=technician)
    with pytest.raises(ValueError, match="closed or cancelled"):
        service.change_status(cancelled_ticket.id, TicketStatus.OPEN, actor=technician)


def test_ticket_service_lists_tickets_assigned_to_technician():
    service = TicketService()
    first = create_sample_ticket(service)
    second = create_sample_ticket(service, title="No funciona el proyector")
    third = create_sample_ticket(service, title="Sin acceso a WiFi")

    service.assign_technician(first.id, technician_id=2)
    service.assign_technician(second.id, technician_id=3)
    service.assign_technician(third.id, technician_id=2)

    assert service.assigned_to(2) == [first, third]
    assert service.assigned_to(999) == []
