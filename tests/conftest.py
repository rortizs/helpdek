from types import SimpleNamespace

import pytest

from app.models.enums import Role
from app.repositories.memory import InMemoryTicketRepository, InMemoryUserRepository
from app.services.notifications import RecordingNotifier
from app.services.tickets import TicketService
from app.services.users import UserService


@pytest.fixture
def user_repository():
    return InMemoryUserRepository()


@pytest.fixture
def ticket_repository():
    return InMemoryTicketRepository()


@pytest.fixture
def notifier():
    return RecordingNotifier()


@pytest.fixture
def users(user_repository):
    service = UserService(user_repository)
    service.register("sofia@school.edu", "Sofía Solicitante", role=Role.REQUESTER)
    service.register("tomas@school.edu", "Tomás Técnico", role=Role.TECHNICIAN)
    service.register("carla@school.edu", "Carla Supervisora", role=Role.SUPERVISOR)
    return service


@pytest.fixture
def tickets(ticket_repository, users, notifier):
    return TicketService(ticket_repository, users, notifier=notifier)


@pytest.fixture
def world(users, tickets, notifier):
    return SimpleNamespace(
        users=users,
        tickets=tickets,
        notifier=notifier,
        requester=users.by_email("sofia@school.edu"),
        technician=users.by_email("tomas@school.edu"),
        supervisor=users.by_email("carla@school.edu"),
    )
