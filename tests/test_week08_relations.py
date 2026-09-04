import pytest

from app.domain.errors import PermissionDeniedError, TicketNotFoundError, ValidationError
from app.models.enums import Role, TicketStatus


def create_sample_ticket(service, requester=None, requester_id=1, **overrides):
    data: dict[str, object] = {
        "title": "No puedo imprimir",
        "description": "La impresora no responde en laboratorio",
        "category": "Hardware",
        "priority": "Medium",
    }
    if requester is not None:
        data["requester"] = requester
    else:
        data["requester_id"] = requester_id
    data.update(overrides)
    return service.create(**data)


def test_category_model_has_identity_and_name():
    from app.models.categories import Category

    category = Category(id=1, name="Hardware")

    assert category.id == 1
    assert category.name == "Hardware"


def test_assign_updates_ticket_and_records_compatibility_assignment(world):
    ticket = create_sample_ticket(world.tickets, requester=world.requester)

    updated = world.tickets.assign(ticket_id=ticket.id, technician_id=world.technician.id)
    assignment = world.tickets.assign_technician(
        ticket_id=ticket.id,
        technician_id=world.technician.id,
    )

    assert updated is ticket
    assert ticket.assignee_id == world.technician.id
    assert assignment.ticket_id == ticket.id
    assert assignment.technician_id == world.technician.id


def test_comment_links_comment_to_ticket(world):
    ticket = create_sample_ticket(world.tickets, requester=world.requester)

    comment = world.tickets.comment(
        ticket.id,
        world.technician,
        "Se revisa el equipo durante el recreo.",
    )

    assert comment.ticket_id == ticket.id
    assert comment.author_id == world.technician.id
    assert comment.body == "Se revisa el equipo durante el recreo."
    assert ticket.comments == [comment]


def test_assign_rejects_unknown_ticket(world):
    with pytest.raises(TicketNotFoundError) as error:
        world.tickets.assign(ticket_id=99, technician_id=world.technician.id)

    assert error.value.properties["ticket_id"] == 99


def test_user_service_creates_users_with_normalized_unique_emails(user_repository):
    from app.services.users import UserService

    service = UserService(user_repository)

    first = service.register(
        "  ANA.TECNICA@School.edu  ",
        "Ana Técnica",
        role=Role.TECHNICIAN,
    )
    second = service.create(name="Bruno Solicitante", email="bruno@school.edu")

    assert first.id == 1
    assert second.id == 2
    assert first.name == "Ana Técnica"
    assert first.email == "ana.tecnica@school.edu"
    assert second.role is Role.REQUESTER
    assert service.require(first.id) is first
    assert service.by_id(999) is None
    with pytest.raises(ValidationError, match="email"):
        service.register(name="Duplicada", email="ana.tecnica@school.edu")


def test_user_service_lists_assignable_staff_in_repository_order(users):
    requester = users.by_email("sofia@school.edu")
    technician = users.by_email("tomas@school.edu")
    supervisor = users.by_email("carla@school.edu")

    assert requester.is_staff is False
    assert technician.is_staff is True
    assert supervisor.is_staff is True
    assert users.technicians() == [technician, supervisor]


def test_assignment_and_comments_record_ticket_history(world):
    ticket = create_sample_ticket(world.tickets, requester=world.requester)

    world.tickets.assign(ticket_id=ticket.id, technician_id=world.technician.id)
    world.tickets.comment(
        ticket.id,
        world.technician,
        "Se revisa el equipo durante el recreo.",
    )

    assert ticket.is_assigned is True
    assert [event.id for event in ticket.history] == [1, 2]
    assert [event.event_type for event in ticket.history] == ["assigned", "commented"]
    assert ticket.history[0].actor_id == world.technician.id
    assert ticket.history[0].detail == f"assigned to {world.technician.name}"
    assert ticket.history[1].detail == "comment added"


def test_change_status_requires_staff_actor_and_records_history(world):
    ticket = create_sample_ticket(world.tickets, requester_id=world.requester.id)

    with pytest.raises(PermissionDeniedError):
        world.tickets.change_status(
            ticket.id,
            TicketStatus.IN_PROGRESS,
            actor=world.requester,
        )

    updated = world.tickets.change_status(
        ticket.id,
        "in_progress",
        actor=world.technician,
    )

    assert updated is ticket
    assert ticket.status is TicketStatus.IN_PROGRESS
    assert ticket.history[-1].event_type == "status_changed"
    assert ticket.history[-1].actor_id == world.technician.id
    assert ticket.history[-1].detail == "in_progress"


def test_change_status_refuses_terminal_tickets(world):
    ticket = create_sample_ticket(world.tickets, requester_id=world.requester.id)

    world.tickets.change_status(ticket.id, TicketStatus.IN_PROGRESS, actor=world.technician)
    world.tickets.change_status(ticket.id, TicketStatus.RESOLVED, actor=world.technician)
    world.tickets.change_status(ticket.id, TicketStatus.CLOSED, actor=world.technician)

    with pytest.raises(ValidationError, match="closed"):
        world.tickets.comment(
            ticket.id,
            world.technician,
            "Comentario tardío",
        )


def test_assign_requires_staff_actor_and_accepts_supervisor_assignee(world):
    requester_ticket = create_sample_ticket(world.tickets, requester=world.requester)
    supervisor_ticket = create_sample_ticket(
        world.tickets,
        requester=world.requester,
        title="Configurar plataforma virtual",
    )

    with pytest.raises(PermissionDeniedError):
        world.tickets.assign(
            requester_ticket.id,
            technician_id=world.technician.id,
            actor=world.requester,
        )

    updated = world.tickets.assign(
        supervisor_ticket.id,
        technician_id=world.supervisor.id,
        actor=world.technician,
    )

    assert updated is supervisor_ticket
    assert supervisor_ticket.assignee_id == world.supervisor.id
    assert supervisor_ticket.history[-1].actor_id == world.technician.id
    assert supervisor_ticket.history[-1].detail == f"assigned to {world.supervisor.name}"


def test_ticket_service_lists_tickets_assigned_to_technician(world):
    first = create_sample_ticket(world.tickets, requester_id=world.requester.id)
    second = create_sample_ticket(
        world.tickets,
        requester_id=world.requester.id,
        title="No funciona el proyector",
    )
    third = create_sample_ticket(
        world.tickets,
        requester_id=world.requester.id,
        title="Sin acceso a WiFi",
    )

    second_technician = world.users.register(
        "valeria@school.edu",
        "Valeria Técnica",
        role=Role.TECHNICIAN,
    )

    world.tickets.assign(first.id, technician_id=world.technician.id)
    world.tickets.assign(second.id, technician_id=second_technician.id)
    world.tickets.assign(third.id, technician_id=world.technician.id)

    assert world.tickets.assigned_to(world.technician.id) == [first, third]
    assert world.tickets.assigned_to(999) == []
