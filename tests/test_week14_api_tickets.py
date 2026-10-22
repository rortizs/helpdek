"""Semana 14: API REST de tickets con FastAPI (primera mitad).

Las peticiones pasan por TestClient contra la base `helpdesk_test` (fixture
`committed_db`): cada peticion abre su propia sesion, confirma o revierte, y
las tablas se reinician con el seed antes de cada prueba.

La identidad llega como token en `Authorization: Bearer` (semana 14, ver
tests/helpers.py). Usuarios del seed: 3 tecnico, 4 y 5 solicitantes.
Desde la semana 14 (jueves) un solicitante solo ve SUS tickets: las lecturas
que necesitan ver todo el seed usan al tecnico.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.dependencies import ServicesDep
from app.core.database import dispose_engine, init_engine, session_scope
from app.domain.clock import now
from app.domain.errors import (
    ConflictError,
    DomainError,
    InvalidStatusTransitionError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.main import create_app
from app.models.enums import TicketStatus
from app.repositories.sqlalchemy import SqlAlchemyUserRepository
from app.schemas.tickets import TicketOut
from tests.helpers import auth_headers

REQUESTER = auth_headers(5)
TECHNICIAN = auth_headers(3)
NEW_TICKET = {
    "title": "Teclado roto",
    "description": "Faltan teclas",
    "category": "Hardware",
    "priority": "Low",
}


@pytest.fixture
def client(committed_db):
    return TestClient(create_app())


def assert_error(response, status_code, code):
    """Todos los errores comparten el mismo sobre: error, message, details."""
    assert response.status_code == status_code
    body = response.json()
    assert set(body) == {"error", "message", "details"}
    assert body["error"] == code
    assert isinstance(body["message"], str) and body["message"]
    assert isinstance(body["details"], dict)
    return body


# --- salud ------------------------------------------------------------------

def test_health_checks_the_database(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_returns_503_when_the_database_is_down():
    init_engine("postgresql+psycopg://helpdesk:helpdesk@localhost:5999/helpdesk_test")
    try:
        response = TestClient(create_app()).get("/api/health")
    finally:
        dispose_engine()

    body = assert_error(response, 503, "database_unavailable")
    assert "helpdesk:" not in body["message"]  # nunca filtrar credenciales


# --- identidad temporal -----------------------------------------------------

@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer basura"},
        auth_headers(999),  # token valido de un usuario que no existe
        {"X-User-Id": "3"},  # el encabezado temporal de la semana 14 ya no autentica
    ],
)
def test_requests_without_a_known_user_get_401(client, headers):
    response = client.get("/api/tickets", headers=headers)

    assert_error(response, 401, "unauthenticated")


# --- GET /api/tickets -------------------------------------------------------

def test_list_returns_the_seeded_tickets(client):
    response = client.get("/api/tickets", headers=TECHNICIAN)

    assert response.status_code == 200
    tickets = response.json()
    assert sorted(ticket["id"] for ticket in tickets) == [1, 2, 3, 4, 5, 6]
    first = next(ticket for ticket in tickets if ticket["id"] == 1)
    assert set(first) == {
        "id", "title", "description", "category", "priority", "status",
        "requester_id", "assignee_id", "created_at", "updated_at", "due_at",
        "is_overdue",
    }
    assert first["status"] == "open"
    assert first["assignee_id"] is None


def test_list_filters_by_status_requester_and_assignee(client):
    def ids(**params):
        response = client.get("/api/tickets", headers=TECHNICIAN, params=params)
        assert response.status_code == 200
        return sorted(ticket["id"] for ticket in response.json())

    assert ids(status="open") == [1, 4]
    assert ids(requester_id=5) == [4, 5, 6]
    assert ids(assignee_id=3) == [2, 3]
    assert ids(status="in_progress", requester_id=5) == [6]


def test_list_with_an_invalid_status_is_422_not_500(client):
    response = client.get("/api/tickets", headers=REQUESTER, params={"status": "Open"})

    body = assert_error(response, 422, "validation_error")
    assert body["details"]["errors"][0]["field"] == "status"


# --- GET /api/tickets/{id} --------------------------------------------------

def test_detail_includes_comments_and_history(client):
    response = client.get("/api/tickets/2", headers=TECHNICIAN)

    assert response.status_code == 200
    ticket = response.json()
    assert ticket["title"] == "Sin acceso al campus"
    assert [comment["author_id"] for comment in ticket["comments"]] == [4, 3]
    assert [event["event_type"] for event in ticket["history"]] == [
        "assigned", "commented", "status_changed", "commented",
    ]


def test_detail_of_a_missing_ticket_is_404(client):
    response = client.get("/api/tickets/999", headers=REQUESTER)

    body = assert_error(response, 404, "ticket_not_found")
    assert body["details"] == {"ticket_id": 999}


def overdue_ticket(status, hours_until_due):
    """Un TicketOut con la fecha limite a `hours_until_due` horas de ahora."""
    moment = now()
    return TicketOut(
        id=1, title="t", description="d", category="General", priority="Low",
        status=status, requester_id=1, assignee_id=None,
        created_at=moment, updated_at=moment,
        due_at=moment + timedelta(hours=hours_until_due),
    )


@pytest.mark.parametrize(
    ("status", "hours_until_due", "expected"),
    [
        (TicketStatus.OPEN, -1, True),
        (TicketStatus.IN_PROGRESS, -1, True),
        (TicketStatus.OPEN, 1, False),         # aun a tiempo
        (TicketStatus.RESOLVED, -1, False),    # ya no esta activo
        (TicketStatus.CLOSED, -1, False),
        (TicketStatus.CANCELLED, -1, False),
    ],
)
def test_is_overdue_depends_on_due_at_and_status(status, hours_until_due, expected):
    # Se prueba la regla con fechas relativas a now(), no con el seed: el seed
    # usa el reloj del servidor de la base (UTC) y Python la hora local.
    assert overdue_ticket(status, hours_until_due).is_overdue is expected


def test_closed_seeded_ticket_is_never_overdue(client):
    assert client.get("/api/tickets/3", headers=TECHNICIAN).json()["is_overdue"] is False


def test_seeded_tickets_are_overdue_according_to_the_local_clock(client):
    # El seed y Python comparten zona (America/Guatemala): ticket 1 es High (SLA 24 h)
    # creado hace 30 h, asi que lleva ~6 h vencido; ticket 2 (Critical, 4 h) creado hace 2 h no.
    def overdue(ticket_id):
        return client.get(f"/api/tickets/{ticket_id}", headers=TECHNICIAN).json()["is_overdue"]

    assert overdue(1) is True
    assert overdue(2) is False
    assert overdue(4) is False  # Medium (2 dias) creado hace 1 dia


# --- POST /api/tickets ------------------------------------------------------

def test_create_returns_201_with_requester_from_the_header(client):
    response = client.post("/api/tickets", headers=REQUESTER, json=NEW_TICKET)

    assert response.status_code == 201
    ticket = response.json()
    assert ticket["id"] > 6
    assert ticket["requester_id"] == 5
    assert ticket["status"] == "open"
    assert ticket["assignee_id"] is None
    assert ticket["due_at"] is not None  # lo calculo el trigger de la base
    assert ticket["is_overdue"] is False


def test_created_ticket_is_persisted_for_the_next_request(client):
    created = client.post("/api/tickets", headers=REQUESTER, json=NEW_TICKET).json()

    stored = client.get(f"/api/tickets/{created['id']}", headers=TECHNICIAN)

    assert stored.status_code == 200
    assert stored.json()["title"] == "Teclado roto"
    assert stored.json()["due_at"] == created["due_at"]


def test_create_ignores_a_status_sent_by_the_client(client):
    response = client.post(
        "/api/tickets",
        headers=REQUESTER,
        json={**NEW_TICKET, "status": TicketStatus.CLOSED.value, "requester_id": 4},
    )

    assert response.status_code == 201
    assert response.json()["status"] == "open"
    assert response.json()["requester_id"] == 5


def test_create_without_identity_is_401(client):
    response = client.post("/api/tickets", json=NEW_TICKET)

    assert_error(response, 401, "unauthenticated")


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"priority": "Urgentisima"}, "priority"),
        ({"category": "Magia"}, "category"),
        ({"title": "ab"}, "title"),
        ({"description": None}, "description"),
    ],
)
def test_create_with_invalid_data_is_422(client, change, field):
    response = client.post("/api/tickets", headers=REQUESTER, json={**NEW_TICKET, **change})

    body = assert_error(response, 422, "validation_error")
    assert [error["field"] for error in body["details"]["errors"]] == [field]
    assert len(client.get("/api/tickets", headers=TECHNICIAN).json()) == 6  # no se guardo nada


# --- una peticion es una unidad de trabajo ----------------------------------

def test_a_failing_request_rolls_back_everything_it_wrote(client):
    @client.app.post("/boom-after-write")
    def boom_after_write(services: ServicesDep):
        services.users.register("fantasma@school.edu", "Fantasma")
        raise ConflictError("fallo despues de escribir")

    assert client.post("/boom-after-write").status_code == 409

    with session_scope() as session:
        assert SqlAlchemyUserRepository(session).by_email("fantasma@school.edu") is None


def test_the_client_never_gets_a_2xx_when_the_commit_fails(client, monkeypatch):
    """El COMMIT ocurre ANTES de enviar la respuesta.

    Si el commit corriera despues (al cerrar la peticion), el cliente ya habria
    recibido un 201 de algo que la base rechazo. Por eso get_db se declara con
    scope="function": termina junto con la ruta, no junto con la respuesta.
    """
    def failing_commit(self):
        raise RuntimeError("el COMMIT fallo")

    # raise_server_exceptions=False: queremos ver la respuesta, no la excepcion.
    unsafe_client = TestClient(client.app, raise_server_exceptions=False)
    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", failing_commit)
        response = unsafe_client.post("/api/tickets", headers=REQUESTER, json=NEW_TICKET)

    assert response.status_code == 500
    assert not response.is_success
    # Con el commit ya restaurado: nada de la peticion quedo guardado.
    assert len(client.get("/api/tickets", headers=TECHNICIAN).json()) == 6


# --- errores de dominio -> respuestas HTTP ----------------------------------

@pytest.mark.parametrize(
    ("error", "status_code", "code"),
    [
        (NotFoundError("ticket", 1), 404, "not_found"),
        (PermissionDeniedError("nope", actor_id=3), 403, "permission_denied"),
        (InvalidStatusTransitionError("open", "closed"), 409, "invalid_status_transition"),
        (ConflictError("duplicated", field="email"), 409, "conflict"),
        (ValidationError("bad", field="title"), 422, "validation_error"),
        (DomainError("something else"), 400, "domain_error"),
    ],
)
def test_domain_errors_map_to_http_errors(error, status_code, code):
    app = create_app()

    @app.get("/api/boom")
    def boom():
        raise error

    response = TestClient(app).get("/api/boom")

    body = assert_error(response, status_code, code)
    assert body["details"] == error.properties
