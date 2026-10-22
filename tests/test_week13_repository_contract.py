"""22/10/2026 - Semana 13: el contrato del repositorio crecio (ejercicios 1 y 2).

Aqui verifico, con el MISMO conjunto de pruebas, que la implementacion en memoria
y la de PostgreSQL cumplen el contrato ampliado: `by_category`, `count_by_status`,
filtros por categoria/prioridad en `list()` y `commit()/rollback()`. Si las dos
pasan las mismas pruebas, el servicio puede cambiar de repositorio sin enterarse.
"""

from __future__ import annotations

import pytest

from app.models.enums import Role, TicketStatus
from app.repositories.memory import InMemoryTicketRepository
from app.repositories.sqlalchemy import SqlAlchemyTicketRepository, SqlAlchemyUserRepository
from app.services.notifications import RecordingNotifier
from app.services.tickets import TicketService
from app.services.users import UserService


# 22/10/2026 - Semana 17: la variante "postgres" pide la fixture `db` en tiempo de ejecucion (getfixturevalue),
# asi que conftest no la ve; la marco yo como integracion para que `-m "not integration"` no necesite PostgreSQL.
@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.integration)])
def contract(request):
    """22/10/2026 - Devuelvo (repositorio, servicio, solicitante) para cada implementacion."""
    if request.param == "memory":
        from app.repositories.memory import InMemoryUserRepository

        users = UserService(InMemoryUserRepository())
        repository = InMemoryTicketRepository()
    else:
        db = request.getfixturevalue("db")
        users = UserService(SqlAlchemyUserRepository(db))
        repository = SqlAlchemyTicketRepository(db)
    requester = users.register("contrato@school.edu", "Contrato", role=Role.REQUESTER)
    service = TicketService(repository, users, notifier=RecordingNotifier())
    return repository, service, requester


def _create(service, requester, category, priority, title="Ticket de contrato"):
    return service.create(
        title=title,
        description="descripcion",
        category=category,
        priority=priority,
        requester=requester,
    )


def test_by_category_returns_only_that_category(contract):
    repository, service, requester = contract
    hardware = _create(service, requester, "Hardware", "Low")
    _create(service, requester, "Network", "Low")

    found = repository.by_category("Hardware")

    assert hardware.id in {ticket.id for ticket in found}
    assert {ticket.category for ticket in found} == {"Hardware"}


def test_list_filters_by_category_and_priority_together(contract):
    repository, service, requester = contract
    target = _create(service, requester, "Software", "Critical")
    _create(service, requester, "Software", "Low")
    _create(service, requester, "Network", "Critical")

    found = repository.list(category="Software", priority="Critical")

    assert target.id in {ticket.id for ticket in found}
    assert {(ticket.category, ticket.priority) for ticket in found} == {("Software", "Critical")}


def test_count_by_status_counts_every_status(contract):
    repository, service, requester = contract
    before = repository.count_by_status()
    _create(service, requester, "Other", "Low")
    _create(service, requester, "Other", "Low")

    after = repository.count_by_status()

    assert after.get("open", 0) == before.get("open", 0) + 2
    assert sum(after.values()) == sum(before.values()) + 2


def test_commit_and_rollback_exist_on_the_contract(contract):
    repository, _, _ = contract

    # No lanzan error en ninguna implementacion (en memoria no hacen nada).
    assert repository.commit() is None
    assert repository.rollback() is None


def test_postgres_rollback_discards_the_pending_insert(db):
    users = UserService(SqlAlchemyUserRepository(db))
    repository = SqlAlchemyTicketRepository(db)
    requester = users.register("rollback@school.edu", "Rollback", role=Role.REQUESTER)
    service = TicketService(repository, users, notifier=RecordingNotifier())
    db.commit()  # el solicitante queda confirmado; el ticket de abajo no

    ticket = _create(service, requester, "General", "Low")
    repository.rollback()

    assert repository.by_id(ticket.id) is None
    assert users.by_email("rollback@school.edu") is not None


def test_status_filter_still_accepts_strings(contract):
    # PRESERVE: el filtro por estado que existia desde la semana 9 sigue igual.
    repository, service, requester = contract
    ticket = _create(service, requester, "General", "Low")

    found = repository.list(status="open")

    assert ticket.id in {item.id for item in found}
    assert all(item.status is TicketStatus.OPEN for item in found)
