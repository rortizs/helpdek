"""Semana 14 (jueves): el resto de la API REST.

PRUEBAS DE ACEPTACION. Tu trabajo es escribir el codigo de `app/` para que
todas pasen; no las modifiques. Corre:

    uv run pytest tests/test_week14_api_recursos.py -q

Necesitas PostgreSQL arriba (docker compose up -d db): sin el, las pruebas que
usan la base se omiten. Cada prueba parte del seed (docs/database/seed.sql).

Usuarios del seed (cada uno se identifica con su token, ver tests/helpers.py):
    1 administrador | 2 supervisor | 3 y 6 tecnicos | 4 y 5 solicitantes
Tickets del seed (solicitante / tecnico / estado):
    1: 4 / -  / open        2: 4 / 3 / in_progress   3: 4 / 3 / closed
    4: 5 / -  / open        5: 5 / 6 / resolved      6: 5 / 6 / in_progress

Que debes construir, siguiendo el patron del martes (esquema -> servicio ->
ruta; las reglas viven en el SERVICIO, la ruta solo traduce):

 1. Usuarios      app/api/routes/users.py, app/schemas/users.py
 2. Comentarios   GET/POST /api/tickets/{id}/comments
 3. Acciones      assign, status, priority, cancel
 4. Avisos        app/api/routes/notifications.py
 5. Permisos de lectura (en TicketService, no solo en las rutas)
 6. Filtros y paginacion hechos en SQL, con el encabezado X-Total-Count
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text

from app.api.dependencies import DbSession, get_services
from app.core.database import session_scope
from app.core.services import build_services
from app.domain.errors import TicketNotFoundError
from app.main import create_app
from app.repositories.sqlalchemy import (
    HistoryEventORM,
    NotificationORM,
    SqlAlchemyNotificationRepository,
    SqlAlchemyTicketRepository,
)
from app.services.notifications import DatabaseNotifier
from tests.helpers import auth_headers

ADMIN = auth_headers(1)
SUPERVISOR = auth_headers(2)
TECHNICIAN = auth_headers(3)
OWNER = auth_headers(4)      # solicitante de los tickets 1, 2 y 3
OTHER_REQUESTER = auth_headers(5)  # solicitante de los tickets 4, 5 y 6
NEW_TICKET = {
    "title": "Teclado roto",
    "description": "Faltan teclas",
    "category": "Hardware",
    "priority": "Low",
}


@pytest.fixture
def client(committed_db):
    # 22/10/2026 - Con `with`, el lifespan cierra el pool de conexiones de la app al terminar.
    with TestClient(create_app()) as test_client:
        yield test_client


def assert_error(response, status_code, code):
    """Todos los errores comparten el mismo sobre: error, message, details."""
    assert response.status_code == status_code, response.text
    body = response.json()
    assert set(body) == {"error", "message", "details"}
    assert body["error"] == code
    return body


def ids(response):
    assert response.status_code == 200, response.text
    return [ticket["id"] for ticket in response.json()]


# =============================================================================
# 1. Usuarios
# =============================================================================

def test_me_returns_the_current_user(client):
    response = client.get("/api/users/me", headers=OWNER)

    assert response.status_code == 200
    assert response.json() == {
        "id": 4,
        "name": "Requester",
        "email": "requester@example.com",
        "role": "requester",
    }


def test_users_never_expose_password_hash(client):
    me = client.get("/api/users/me", headers=OWNER).json()
    listed = client.get("/api/users", headers=ADMIN).json()
    single = client.get("/api/users/3", headers=ADMIN).json()

    for user in [me, single, *listed]:
        assert "password_hash" not in user
        assert set(user) == {"id", "name", "email", "role"}


def test_staff_can_list_all_users(client):
    response = client.get("/api/users", headers=TECHNICIAN)

    assert response.status_code == 200
    assert [user["id"] for user in response.json()] == [1, 2, 3, 4, 5, 6]


def test_users_can_be_filtered_by_role(client):
    response = client.get("/api/users", headers=TECHNICIAN, params={"role": "technician"})

    assert [user["id"] for user in response.json()] == [3, 6]


def test_filtering_users_by_an_unknown_role_is_422(client):
    response = client.get("/api/users", headers=TECHNICIAN, params={"role": "jefe"})

    assert_error(response, 422, "validation_error")


def test_requester_cannot_list_users(client):
    response = client.get("/api/users", headers=OWNER)

    assert_error(response, 403, "permission_denied")


def test_staff_can_read_any_user(client):
    response = client.get("/api/users/5", headers=TECHNICIAN)

    assert response.status_code == 200
    assert response.json()["email"] == "ana@umg.edu"


def test_a_requester_can_read_their_own_user(client):
    response = client.get("/api/users/4", headers=OWNER)

    assert response.status_code == 200
    assert response.json()["id"] == 4


def test_a_requester_cannot_read_another_user(client):
    response = client.get("/api/users/5", headers=OWNER)

    assert_error(response, 403, "permission_denied")


def test_reading_a_missing_user_is_404_for_staff(client):
    response = client.get("/api/users/999", headers=TECHNICIAN)

    body = assert_error(response, 404, "user_not_found")
    assert body["details"] == {"user_id": 999}


def test_administrator_can_create_a_user(client):
    response = client.post(
        "/api/users",
        headers=ADMIN,
        json={"name": "Luis Tecnico", "email": "Luis@UMG.edu", "role": "technician"},
    )

    assert response.status_code == 201
    created = response.json()
    assert created["email"] == "luis@umg.edu"  # el servicio normaliza el correo
    assert created["role"] == "technician"
    assert created["id"] > 6
    # Persistido: otra peticion lo encuentra.
    assert client.get(f"/api/users/{created['id']}", headers=ADMIN).status_code == 200


def test_new_users_are_requesters_by_default(client):
    response = client.post(
        "/api/users", headers=ADMIN, json={"name": "Nuevo", "email": "nuevo@umg.edu"}
    )

    assert response.status_code == 201
    assert response.json()["role"] == "requester"


@pytest.mark.parametrize("headers", [SUPERVISOR, TECHNICIAN, OWNER])
def test_only_the_administrator_can_create_users(client, headers):
    response = client.post(
        "/api/users", headers=headers, json={"name": "Intruso", "email": "intruso@umg.edu"}
    )

    assert_error(response, 403, "permission_denied")
    assert len(client.get("/api/users", headers=ADMIN).json()) == 6


def test_creating_a_user_with_a_duplicate_email_is_409(client):
    response = client.post(
        "/api/users", headers=ADMIN, json={"name": "Otra Ana", "email": "ANA@umg.edu"}
    )

    body = assert_error(response, 409, "conflict")
    assert body["details"]["field"] == "email"


def test_creating_a_user_with_an_invalid_role_is_422(client):
    response = client.post(
        "/api/users",
        headers=ADMIN,
        json={"name": "Raro", "email": "raro@umg.edu", "role": "jefe"},
    )

    body = assert_error(response, 422, "validation_error")
    assert body["details"]["errors"][0]["field"] == "role"


@pytest.mark.parametrize("email", ["sin-arroba", "con espacio@umg.edu", ""])
def test_creating_a_user_with_an_invalid_email_is_422(client, email):
    response = client.post("/api/users", headers=ADMIN, json={"name": "Raro", "email": email})

    body = assert_error(response, 422, "validation_error")
    assert body["details"]["errors"][0]["field"] == "email"


# =============================================================================
# 2. Comentarios
# =============================================================================

def test_list_comments_of_a_ticket_in_order(client):
    response = client.get("/api/tickets/2/comments", headers=OWNER)

    assert response.status_code == 200
    comments = response.json()
    assert [comment["author_id"] for comment in comments] == [4, 3]
    assert set(comments[0]) == {"id", "ticket_id", "author_id", "body", "created_at"}


def test_listing_comments_of_a_missing_ticket_is_404(client):
    response = client.get("/api/tickets/999/comments", headers=TECHNICIAN)

    assert_error(response, 404, "ticket_not_found")


def test_add_comment_returns_201_and_the_author_is_the_current_user(client):
    response = client.post(
        "/api/tickets/1/comments", headers=OWNER, json={"body": "  Sigue sin imagen  "}
    )

    assert response.status_code == 201
    comment = response.json()
    assert comment["author_id"] == 4
    assert comment["ticket_id"] == 1
    assert comment["body"] == "Sigue sin imagen"
    assert comment["id"] is not None


def test_a_client_cannot_choose_the_author_of_a_comment(client):
    response = client.post(
        "/api/tickets/1/comments", headers=OWNER, json={"body": "Hola", "author_id": 3}
    )

    assert response.status_code == 201
    assert response.json()["author_id"] == 4


def test_a_new_comment_shows_up_in_the_ticket_detail_and_history(client):
    client.post("/api/tickets/1/comments", headers=TECHNICIAN, json={"body": "Voy para alla"})

    detail = client.get("/api/tickets/1", headers=OWNER).json()

    assert [comment["body"] for comment in detail["comments"]] == ["Voy para alla"]
    assert [event["event_type"] for event in detail["history"]] == ["commented"]


@pytest.mark.parametrize("body", ["", "   "])
def test_an_empty_comment_is_422(client, body):
    response = client.post("/api/tickets/1/comments", headers=OWNER, json={"body": body})

    assert_error(response, 422, "validation_error")
    assert client.get("/api/tickets/1/comments", headers=OWNER).json() == []


def test_cannot_comment_on_a_closed_ticket(client):
    response = client.post("/api/tickets/3/comments", headers=TECHNICIAN, json={"body": "Tarde"})

    assert_error(response, 422, "validation_error")


def test_cannot_comment_on_a_cancelled_ticket(client):
    assert client.post("/api/tickets/1/cancel", headers=OWNER).status_code == 200

    response = client.post("/api/tickets/1/comments", headers=OWNER, json={"body": "Tarde"})

    assert_error(response, 422, "validation_error")


# =============================================================================
# 3. Acciones sobre un ticket (cada una devuelve el TicketOut actualizado)
# =============================================================================

def test_staff_can_assign_a_ticket(client):
    response = client.post("/api/tickets/1/assign", headers=SUPERVISOR, json={"technician_id": 3})

    assert response.status_code == 200
    ticket = response.json()
    assert ticket["id"] == 1
    assert ticket["assignee_id"] == 3
    detail = client.get("/api/tickets/1", headers=TECHNICIAN).json()
    assert detail["history"][-1]["event_type"] == "assigned"
    assert detail["history"][-1]["actor_id"] == 2  # quien asigno, no el tecnico


def test_a_requester_cannot_assign_tickets(client):
    response = client.post("/api/tickets/1/assign", headers=OWNER, json={"technician_id": 3})

    assert_error(response, 403, "permission_denied")
    assert client.get("/api/tickets/1", headers=OWNER).json()["assignee_id"] is None


def test_the_assignee_must_be_support_staff(client):
    response = client.post("/api/tickets/1/assign", headers=TECHNICIAN, json={"technician_id": 5})

    body = assert_error(response, 422, "validation_error")
    assert body["details"]["field"] == "technician_id"


def test_assigning_to_an_unknown_user_is_404(client):
    response = client.post("/api/tickets/1/assign", headers=TECHNICIAN, json={"technician_id": 999})

    assert_error(response, 404, "user_not_found")


def test_assign_needs_a_technician_id(client):
    response = client.post("/api/tickets/1/assign", headers=TECHNICIAN, json={})

    body = assert_error(response, 422, "validation_error")
    assert body["details"]["errors"][0]["field"] == "technician_id"


def test_staff_can_change_the_status_following_the_workflow(client):
    response = client.patch("/api/tickets/1/status", headers=TECHNICIAN, json={"status": "in_progress"})

    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"
    assert client.get("/api/tickets/1", headers=OWNER).json()["status"] == "in_progress"


def test_an_invalid_status_transition_is_409(client):
    response = client.patch("/api/tickets/1/status", headers=TECHNICIAN, json={"status": "closed"})

    body = assert_error(response, 409, "invalid_status_transition")
    assert body["details"] == {"from_status": "open", "to_status": "closed"}
    assert client.get("/api/tickets/1", headers=OWNER).json()["status"] == "open"


def test_an_unknown_status_value_is_422(client):
    response = client.patch("/api/tickets/1/status", headers=TECHNICIAN, json={"status": "Open"})

    assert_error(response, 422, "validation_error")


def test_a_requester_cannot_change_the_status(client):
    response = client.patch("/api/tickets/1/status", headers=OWNER, json={"status": "in_progress"})

    assert_error(response, 403, "permission_denied")


def test_staff_can_change_the_priority_and_due_at_is_recalculated(client):
    before = client.get("/api/tickets/1", headers=TECHNICIAN).json()
    assert before["priority"] == "High"

    response = client.patch("/api/tickets/1/priority", headers=TECHNICIAN, json={"priority": "Critical"})

    assert response.status_code == 200
    after = response.json()
    assert after["priority"] == "Critical"
    assert after["due_at"] != before["due_at"]
    # El trigger de la base recalculo el SLA: Critical = created_at + 4 horas.
    with session_scope() as session:
        due_at, created_at = session.execute(
            text("SELECT due_at, created_at FROM tickets WHERE id = 1")
        ).one()
    assert (due_at - created_at).total_seconds() == 4 * 3600
    assert after["due_at"] == due_at.isoformat()


def test_changing_the_priority_records_history(client):
    client.patch("/api/tickets/1/priority", headers=TECHNICIAN, json={"priority": "Low"})

    event = client.get("/api/tickets/1", headers=TECHNICIAN).json()["history"][-1]

    assert event["event_type"] == "priority_changed"
    assert event["actor_id"] == 3


def test_an_invalid_priority_is_422(client):
    response = client.patch("/api/tickets/1/priority", headers=TECHNICIAN, json={"priority": "Urgentisima"})

    assert_error(response, 422, "validation_error")
    assert client.get("/api/tickets/1", headers=TECHNICIAN).json()["priority"] == "High"


def test_a_requester_cannot_change_the_priority(client):
    response = client.patch("/api/tickets/1/priority", headers=OWNER, json={"priority": "Low"})

    assert_error(response, 403, "permission_denied")


def test_the_requester_can_cancel_their_own_ticket(client):
    response = client.post("/api/tickets/1/cancel", headers=OWNER)

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_only_the_requester_of_the_ticket_can_cancel_it(client):
    by_staff = client.post("/api/tickets/1/cancel", headers=TECHNICIAN)
    by_other_requester = client.post("/api/tickets/1/cancel", headers=OTHER_REQUESTER)

    assert_error(by_staff, 403, "permission_denied")
    assert_error(by_other_requester, 403, "permission_denied")
    assert client.get("/api/tickets/1", headers=OWNER).json()["status"] == "open"


def test_a_closed_ticket_cannot_be_cancelled(client):
    response = client.post("/api/tickets/3/cancel", headers=OWNER)

    assert_error(response, 409, "invalid_status_transition")


def test_actions_on_a_missing_ticket_are_404(client):
    responses = [
        client.post("/api/tickets/999/assign", headers=TECHNICIAN, json={"technician_id": 3}),
        client.patch("/api/tickets/999/status", headers=TECHNICIAN, json={"status": "open"}),
        client.patch("/api/tickets/999/priority", headers=TECHNICIAN, json={"priority": "Low"}),
        client.post("/api/tickets/999/cancel", headers=OWNER),
    ]

    for response in responses:
        assert_error(response, 404, "ticket_not_found")


def test_a_requester_gets_403_not_404_on_staff_actions_for_missing_tickets(client):
    # El permiso se revisa antes de buscar el ticket: asi un solicitante no
    # puede averiguar que ids existen mirando la diferencia entre 403 y 404.
    responses = [
        client.post("/api/tickets/999/assign", headers=OWNER, json={"technician_id": 3}),
        client.patch("/api/tickets/999/status", headers=OWNER, json={"status": "open"}),
        client.patch("/api/tickets/999/priority", headers=OWNER, json={"priority": "Low"}),
    ]

    for response in responses:
        assert_error(response, 403, "permission_denied")


class ExplodingNotifier(DatabaseNotifier):
    """Guarda el aviso y LUEGO falla: la accion queda a medias."""

    def notify(self, *args, **kwargs):
        super().notify(*args, **kwargs)
        raise RuntimeError("el servicio de avisos se cayo")


def test_a_failing_action_leaves_no_partial_rows(committed_db):
    app = create_app()

    def services_with_exploding_notifier(db: DbSession):
        services = get_services(db)
        _, tickets = build_services(
            db, notifier=ExplodingNotifier(SqlAlchemyNotificationRepository(db))
        )
        return services._replace(tickets=tickets)

    app.dependency_overrides[get_services] = services_with_exploding_notifier
    # raise_server_exceptions=False: queremos ver la respuesta 500, no la excepcion.
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post("/api/tickets/1/assign", headers=TECHNICIAN, json={"technician_id": 3})

    assert response.status_code == 500
    with session_scope() as session:
        ticket = SqlAlchemyTicketRepository(session).by_id(1)
        assert ticket.assignee_id is None  # el UPDATE del ticket se revirtio
        assert ticket.history == []        # y tambien el evento de historial
        assert session.scalar(
            select(func.count()).select_from(HistoryEventORM).where(HistoryEventORM.ticket_id == 1)
        ) == 0
        assert session.scalar(
            select(func.count()).select_from(NotificationORM).where(NotificationORM.ticket_id == 1)
        ) == 0  # tampoco el aviso que ya se habia escrito


# =============================================================================
# 4. Avisos (notificaciones)
# =============================================================================

def test_notifications_returns_only_unread_ones_of_the_current_user(client):
    response = client.get("/api/notifications", headers=OWNER)

    assert response.status_code == 200
    notifications = response.json()
    assert len(notifications) == 2  # el seed deja 2 sin leer para el usuario 4
    assert {n["type"] for n in notifications} == {"ticket_commented", "ticket_status_changed"}
    assert all(n["read_at"] is None for n in notifications)
    assert set(notifications[0]) == {
        "id", "ticket_id", "title", "message", "type", "read_at", "created_at",
    }


def test_a_user_without_unread_notifications_gets_an_empty_list(client):
    assert client.get("/api/notifications", headers=TECHNICIAN).json() == []


def test_assigning_a_ticket_notifies_the_technician(client):
    client.post("/api/tickets/1/assign", headers=SUPERVISOR, json={"technician_id": 3})

    notifications = client.get("/api/notifications", headers=TECHNICIAN).json()

    assert [(n["type"], n["ticket_id"]) for n in notifications] == [("ticket_assigned", 1)]
    assert notifications[0]["title"] == "Ticket asignado"


def test_read_all_marks_them_and_returns_how_many(client):
    response = client.post("/api/notifications/read-all", headers=OWNER)

    assert response.status_code == 200
    assert response.json() == {"updated": 2}
    assert client.get("/api/notifications", headers=OWNER).json() == []
    assert client.post("/api/notifications/read-all", headers=OWNER).json() == {"updated": 0}


def test_read_all_does_not_touch_other_users_notifications(client):
    client.post("/api/notifications/read-all", headers=OWNER)

    assert len(client.get("/api/notifications", headers=OTHER_REQUESTER).json()) == 1


# =============================================================================
# 5. Permisos de lectura (se aplican en TicketService, la ruta solo los usa)
# =============================================================================

def test_a_requester_only_sees_their_own_tickets(client):
    assert sorted(ids(client.get("/api/tickets", headers=OWNER))) == [1, 2, 3]
    assert sorted(ids(client.get("/api/tickets", headers=OTHER_REQUESTER))) == [4, 5, 6]


def test_staff_see_all_the_tickets(client):
    for headers in (TECHNICIAN, SUPERVISOR, ADMIN):
        assert sorted(ids(client.get("/api/tickets", headers=headers))) == [1, 2, 3, 4, 5, 6]


def test_a_requester_cannot_widen_the_list_with_requester_id(client):
    response = client.get("/api/tickets", headers=OWNER, params={"requester_id": 5})

    assert ids(response) == []
    assert response.headers["X-Total-Count"] == "0"


def test_a_requester_sees_their_own_tickets_when_filtering_by_themselves(client):
    assert sorted(ids(client.get("/api/tickets", headers=OWNER, params={"requester_id": 4}))) == [1, 2, 3]


def test_the_detail_of_another_requesters_ticket_is_404(client):
    response = client.get("/api/tickets/4", headers=OWNER)

    body = assert_error(response, 404, "ticket_not_found")
    # Misma respuesta que un ticket inexistente: no se revela que existe.
    missing = client.get("/api/tickets/999", headers=OWNER)
    assert body["message"].replace("4", "N") == missing.json()["message"].replace("999", "N")


def test_the_comments_of_another_requesters_ticket_are_404(client):
    assert_error(client.get("/api/tickets/4/comments", headers=OWNER), 404, "ticket_not_found")


def test_a_requester_cannot_comment_on_another_requesters_ticket(client):
    response = client.post("/api/tickets/4/comments", headers=OWNER, json={"body": "Hola"})

    assert_error(response, 404, "ticket_not_found")
    assert client.get("/api/tickets/4/comments", headers=TECHNICIAN).json() == []


def test_staff_can_read_any_ticket_and_its_comments(client):
    assert client.get("/api/tickets/4", headers=TECHNICIAN).status_code == 200
    assert client.get("/api/tickets/2/comments", headers=TECHNICIAN).status_code == 200


# --- los mismos permisos, directo sobre el servicio (repositorios en memoria) --

@pytest.fixture
def second_requester(world):
    return world.users.register("pedro@school.edu", "Pedro Solicitante")


def create_ticket(world, requester, title="Proyector danado"):
    return world.tickets.create(
        title=title, description="No enciende", category="Hardware",
        priority="High", requester=requester,
    )


def test_service_list_for_scopes_a_requester_to_their_own_tickets(world, second_requester):
    mine = create_ticket(world, world.requester)
    create_ticket(world, second_requester)

    page = world.tickets.list_for(world.requester)

    assert [ticket.id for ticket in page.items] == [mine.id]
    assert page.total == 1


def test_service_list_for_gives_staff_every_ticket(world, second_requester):
    create_ticket(world, world.requester)
    create_ticket(world, second_requester)

    assert world.tickets.list_for(world.technician).total == 2


def test_service_require_for_hides_other_requesters_tickets(world, second_requester):
    ticket = create_ticket(world, world.requester)

    with pytest.raises(TicketNotFoundError):
        world.tickets.require_for(second_requester, ticket.id)

    assert world.tickets.require_for(world.requester, ticket.id) is ticket
    assert world.tickets.require_for(world.technician, ticket.id) is ticket


def test_service_comment_on_a_hidden_ticket_is_not_found(world, second_requester):
    ticket = create_ticket(world, world.requester)

    with pytest.raises(TicketNotFoundError):
        world.tickets.comment(ticket.id, author=second_requester, body="Hola")

    assert ticket.comments == []


# =============================================================================
# 6. Filtros y paginacion en SQL
# =============================================================================

def test_default_page_size_is_20_and_the_total_is_in_a_header(client):
    for number in range(17):
        client.post("/api/tickets", headers=OWNER, json={**NEW_TICKET, "title": f"Ticket {number:02d}"})

    response = client.get("/api/tickets", headers=TECHNICIAN)

    assert len(ids(response)) == 20
    assert response.headers["X-Total-Count"] == "23"


def test_limit_and_offset_slice_the_list_newest_first(client):
    # Orden por created_at descendente. En el seed: 2 (hace 2 h), 4 (1 dia),
    # 1 (30 h), 6 (3 dias), 5 (5 dias), 3 (10 dias).
    assert ids(client.get("/api/tickets", headers=TECHNICIAN)) == [2, 4, 1, 6, 5, 3]

    first = client.get("/api/tickets", headers=TECHNICIAN, params={"limit": 2})
    second = client.get("/api/tickets", headers=TECHNICIAN, params={"limit": 2, "offset": 2})
    last = client.get("/api/tickets", headers=TECHNICIAN, params={"limit": 2, "offset": 5})

    assert ids(first) == [2, 4]
    assert ids(second) == [1, 6]
    assert ids(last) == [3]
    for response in (first, second, last):
        assert response.headers["X-Total-Count"] == "6"  # el total ignora la pagina


def test_an_offset_past_the_end_is_an_empty_list_with_the_real_total(client):
    response = client.get("/api/tickets", headers=TECHNICIAN, params={"offset": 50})

    assert ids(response) == []
    assert response.headers["X-Total-Count"] == "6"


def test_tickets_with_the_same_date_are_ordered_by_id_descending(client):
    with session_scope() as session:
        for title in ("Gemelo A", "Gemelo B", "Gemelo C"):
            session.execute(
                text(
                    "INSERT INTO tickets (title, description, category, priority, requester_id, "
                    "created_at, updated_at) VALUES (:title, 'x', 'Other', 'Low', 4, "
                    "'2099-01-01 10:00', '2099-01-01 10:00')"
                ),
                {"title": title},
            )

    listed = ids(client.get("/api/tickets", headers=TECHNICIAN, params={"limit": 3}))

    assert listed == sorted(listed, reverse=True)
    assert min(listed) > 6


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"status": "open"}, {1, 4}),
        ({"category": "Hardware"}, {1, 3}),
        ({"priority": "Medium"}, {4, 5}),
        ({"assignee_id": 6}, {5, 6}),
        ({"requester_id": 5}, {4, 5, 6}),
        ({"status": "in_progress", "priority": "High"}, {6}),
        ({"category": "Software", "assignee_id": 6, "status": "resolved"}, {5}),
        ({"category": "Network", "priority": "Critical"}, set()),
    ],
)
def test_filters_combine_with_and(client, params, expected):
    response = client.get("/api/tickets", headers=TECHNICIAN, params=params)

    assert set(ids(response)) == expected
    assert response.headers["X-Total-Count"] == str(len(expected))


def test_the_total_count_follows_the_filters_not_the_page(client):
    response = client.get("/api/tickets", headers=TECHNICIAN, params={"status": "open", "limit": 1})

    assert len(ids(response)) == 1
    assert response.headers["X-Total-Count"] == "2"


@pytest.mark.parametrize(
    ("params", "field"),
    [
        ({"status": "Open"}, "status"),
        ({"category": "Magia"}, "category"),
        ({"priority": "Urgentisima"}, "priority"),
        ({"limit": 0}, "limit"),
        ({"limit": 101}, "limit"),
        ({"offset": -1}, "offset"),
        ({"limit": "mucho"}, "limit"),
        ({"assignee_id": "abc"}, "assignee_id"),
    ],
)
def test_invalid_filter_values_are_422(client, params, field):
    response = client.get("/api/tickets", headers=TECHNICIAN, params=params)

    body = assert_error(response, 422, "validation_error")
    reported = body["details"].get("field") or body["details"]["errors"][0]["field"]
    assert reported == field


def test_the_maximum_page_size_is_accepted(client):
    assert client.get("/api/tickets", headers=TECHNICIAN, params={"limit": 100}).status_code == 200


def test_pagination_and_filters_are_executed_by_the_database(db):
    """Prueba de que NO se trae todo a Python: la consulta lleva WHERE, ORDER, LIMIT y COUNT."""
    _, tickets = build_services(db)
    staff = tickets._users.require(3)
    statements: list[str] = []

    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(" ".join(statement.split()))

    event.listen(db.get_bind(), "before_cursor_execute", record)
    page = tickets.list_for(staff, status="open", limit=1, offset=1)
    event.remove(db.get_bind(), "before_cursor_execute", record)

    assert [ticket.id for ticket in page.items] == [1]
    assert page.total == 2
    selects = [sql for sql in statements if "FROM tickets" in sql]
    assert any("LIMIT" in sql and "ORDER BY tickets.created_at DESC, tickets.id DESC" in sql for sql in selects)
    assert any("count(" in sql.lower() for sql in selects)
    assert all("WHERE tickets.status" in sql for sql in selects)


def test_service_list_for_filters_and_paginates_in_memory_too(world):
    for number in range(5):
        create_ticket(world, world.requester, title=f"Ticket {number}")
    world.tickets.assign(2, world.technician.id)

    page = world.tickets.list_for(world.technician, limit=2, offset=1)

    assert [ticket.id for ticket in page.items] == [4, 3]  # mas nuevo primero
    assert page.total == 5
    assert world.tickets.list_for(world.technician, priority="Low").total == 0
    assert world.tickets.list_for(world.technician, assignee_id=world.technician.id).total == 1
