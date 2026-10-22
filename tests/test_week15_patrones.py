"""22/10/2026 - Semana 15: patrones aplicados SOLO donde resuelven un problema real.

Cada bloque de abajo corresponde a un patron y a una decision de docs/decisions/0005:

1. Observer  -> TicketService publica eventos; notificar y auditar son suscriptores.
2. Facade    -> las rutas hablan con UN objeto (HelpDeskFacade), no con cuatro servicios.
3. Inyeccion de dependencias -> con Depends + dependency_overrides cambio piezas sin globals.
4. Singleton (critica) -> el engine ya no es un global del modulo: lo posee cada aplicacion.

No hay un bloque de Decorator: no aparecio una necesidad real (ver el ADR).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.api.dependencies import DbSession, Services, get_facade, get_services
from app.core import database as database_module
from app.core.database import Database
from app.core.security import create_access_token
from app.domain.errors import AuthenticationError, PermissionDeniedError
from app.domain.events import (
    TicketAssigned,
    TicketCancelled,
    TicketCommented,
    TicketCreated,
    TicketStatusChanged,
)
from app.main import create_app
from app.models.entities import Ticket, User
from app.models.enums import Role, TicketStatus
from app.repositories.memory import InMemoryNotificationRepository, InMemoryUserRepository
from app.services.audit import AuditLogSubscriber
from app.services.auth import AuthService
from app.services.helpdesk import HelpDeskFacade
from app.services.notifications import (
    DatabaseNotifier,
    NotificationService,
    RecordingNotifier,
)
from app.services.tickets import TicketService
from app.services.users import UserService
from tests.conftest import TEST_DATABASE_URL
from tests.helpers import assert_is_test_database


# --- 1. Observer: TicketService publica, los suscriptores reaccionan -----------------


def _open_ticket(world):
    return world.tickets.create(
        title="Proyector sin imagen",
        description="Aula A101",
        category="Hardware",
        priority="High",
        requester=world.requester,
    )


def test_creating_a_ticket_publishes_ticket_created(world):
    events = []
    world.tickets.subscribe(events.append)

    ticket = _open_ticket(world)

    assert events == [
        TicketCreated(
            ticket_id=ticket.id,
            actor_id=world.requester.id,
            requester_id=world.requester.id,
            occurred_at=events[0].occurred_at,
        )
    ]


def test_assigning_publishes_ticket_assigned_with_the_technician(world):
    ticket = _open_ticket(world)
    events = []
    world.tickets.subscribe(events.append)

    world.tickets.assign(ticket.id, world.technician.id, actor=world.supervisor)

    (event,) = events
    assert isinstance(event, TicketAssigned)
    assert (event.ticket_id, event.technician_id) == (ticket.id, world.technician.id)
    assert event.actor_id == world.supervisor.id


def test_changing_status_publishes_the_new_status(world):
    ticket = _open_ticket(world)
    world.tickets.assign(ticket.id, world.technician.id, actor=world.supervisor)
    events = []
    world.tickets.subscribe(events.append)

    world.tickets.change_status(ticket.id, TicketStatus.IN_PROGRESS, actor=world.technician)

    (event,) = events
    assert isinstance(event, TicketStatusChanged)
    assert event.new_status is TicketStatus.IN_PROGRESS


def test_commenting_publishes_ticket_commented_with_the_comment_id(world):
    ticket = _open_ticket(world)
    events = []
    world.tickets.subscribe(events.append)

    comment = world.tickets.comment(ticket.id, author=world.technician, body="Voy para alla")

    (event,) = events
    assert isinstance(event, TicketCommented)
    assert event.actor_id == world.technician.id
    assert event.comment_id == comment.id


def test_cancelling_publishes_ticket_cancelled(world):
    ticket = _open_ticket(world)
    events = []
    world.tickets.subscribe(events.append)

    world.tickets.cancel(ticket.id, actor=world.requester)

    (event,) = events
    assert isinstance(event, TicketCancelled)


def test_every_subscriber_receives_every_event_in_order(world):
    first, second = [], []
    world.tickets.subscribe(first.append)
    world.tickets.subscribe(second.append)

    ticket = _open_ticket(world)
    world.tickets.comment(ticket.id, author=world.technician, body="Revisando")

    assert [type(e) for e in first] == [TicketCreated, TicketCommented]
    assert second == first


def test_unsubscribed_callbacks_stop_receiving_events(world):
    events = []
    world.tickets.subscribe(events.append)
    world.tickets.unsubscribe(events.append)

    _open_ticket(world)

    assert events == []


def test_the_notifier_is_just_one_more_subscriber(world):
    # PRESERVE: los mismos avisos de las semanas 7-13, con el mismo texto.
    ticket = _open_ticket(world)
    world.tickets.comment(ticket.id, author=world.technician, body="Revisando")

    titles = [(n.user_id, n.title, n.ticket_id) for n in world.notifier.sent]
    assert titles == [
        (world.requester.id, "ticket_created", ticket.id),
        (world.requester.id, "ticket_commented", ticket.id),
    ]


def test_a_comment_by_the_requester_does_not_notify_the_requester(world):
    # PRESERVE: la regla "no te avisamos de tu propio comentario" sigue viviendo en el notificador.
    ticket = _open_ticket(world)
    world.notifier.sent.clear()

    world.tickets.comment(ticket.id, author=world.requester, body="Sigue igual")

    assert world.notifier.sent == []


def test_a_failing_subscriber_fails_the_operation(world):
    # Decision documentada en el ADR: los suscriptores corren en la MISMA transaccion;
    # si uno falla, la operacion falla y la unidad de trabajo hace rollback.
    def broken(event):
        raise RuntimeError("suscriptor roto")

    world.tickets.subscribe(broken)

    with pytest.raises(RuntimeError, match="suscriptor roto"):
        _open_ticket(world)


def test_audit_subscriber_writes_one_log_line_per_event(world, caplog):
    world.tickets.subscribe(AuditLogSubscriber())

    with caplog.at_level(logging.INFO, logger="helpdesk.audit"):
        ticket = _open_ticket(world)
        world.tickets.comment(ticket.id, author=world.technician, body="Revisando")

    lines = [record.getMessage() for record in caplog.records if record.name == "helpdesk.audit"]
    assert lines == [
        f"event=ticket_created ticket={ticket.id} actor={world.requester.id}",
        f"event=ticket_commented ticket={ticket.id} actor={world.technician.id}",
    ]


def test_legacy_constructor_without_a_notifier_still_works(users, ticket_repository):
    from app.services.tickets import TicketService

    service = TicketService(ticket_repository, users)  # sin notifier ni suscriptores

    ticket = service.create(
        title="Sin notifier",
        description="d",
        category="General",
        priority="Low",
        requester=users.by_email("sofia@school.edu"),
    )

    assert ticket.id is not None


def test_subscribers_can_be_passed_to_the_constructor(users, ticket_repository):
    from app.services.tickets import TicketService

    events = []
    notifier = RecordingNotifier()
    service = TicketService(ticket_repository, users, notifier=notifier, subscribers=[events.append])

    service.create(
        title="Con suscriptor",
        description="d",
        category="General",
        priority="Low",
        requester=users.by_email("sofia@school.edu"),
    )

    assert len(events) == 1 and len(notifier.sent) == 1


# --- 2. Facade: un solo objeto con los casos de uso que necesitan las rutas -----------


@pytest.fixture
def desk(user_repository, ticket_repository):
    """22/10/2026 - Una fachada completa sobre repositorios en memoria (sin PostgreSQL)."""
    users = UserService(user_repository)
    inbox = InMemoryNotificationRepository()
    tickets = TicketService(ticket_repository, users, notifier=DatabaseNotifier(inbox))
    facade = HelpDeskFacade(
        users=users,
        tickets=tickets,
        notifications=NotificationService(inbox),
        auth=AuthService(user_repository),
    )
    return SimpleNamespace(
        facade=facade,
        users=users,
        user_repository=user_repository,
        requester=users.register("sofia@school.edu", "Sofia", role=Role.REQUESTER),
        technician=users.register("tomas@school.edu", "Tomas", role=Role.TECHNICIAN),
        supervisor=users.register("carla@school.edu", "Carla", role=Role.SUPERVISOR),
    )


def test_in_memory_notification_repository_follows_the_contract():
    from app.services.notifications import Notification

    inbox = InMemoryNotificationRepository()
    stored = inbox.add(Notification(user_id=1, title="Hola", message="m", type="ticket_created"))
    inbox.add(Notification(user_id=2, title="Otro", message="m", type="ticket_created"))

    assert stored.id is not None
    assert [n.user_id for n in inbox.unread_for(1)] == [1]
    assert inbox.mark_all_read(1) == 1
    assert inbox.unread_for(1) == []
    assert inbox.mark_all_read(1) == 0


def test_facade_opens_a_ticket_for_the_requester(desk):
    ticket = desk.facade.open_ticket(
        desk.requester,
        title="Wifi caido",
        description="Laboratorio 2",
        category="Network",
        priority="High",
    )

    assert ticket.requester_id == desk.requester.id
    assert ticket.status is TicketStatus.OPEN


def test_facade_runs_a_whole_ticket_story(desk):
    facade = desk.facade
    ticket = facade.open_ticket(
        desk.requester, title="Sin red", description="d", category="Network", priority="Low"
    )

    facade.assign(desk.supervisor, ticket.id, desk.technician.id)
    facade.change_status(desk.technician, ticket.id, TicketStatus.IN_PROGRESS)
    comment = facade.comment(desk.technician, ticket.id, "Ya casi")

    detail = facade.get_ticket(desk.requester, ticket.id)
    assert detail.assignee_id == desk.technician.id
    assert detail.status is TicketStatus.IN_PROGRESS
    assert [c.id for c in facade.list_comments(desk.requester, ticket.id)] == [comment.id]
    assert facade.list_tickets(desk.requester).total == 1


def test_facade_keeps_the_permission_rules_of_the_services(desk):
    ticket = desk.facade.open_ticket(
        desk.requester, title="Sin red", description="d", category="Network", priority="Low"
    )

    with pytest.raises(PermissionDeniedError):
        desk.facade.assign(desk.requester, ticket.id, desk.technician.id)


def test_facade_notifications_are_only_mine_and_can_be_marked_read(desk):
    facade = desk.facade
    ticket = facade.open_ticket(
        desk.requester, title="Sin red", description="d", category="Network", priority="Low"
    )
    facade.assign(desk.supervisor, ticket.id, desk.technician.id)

    assert [n.type for n in facade.my_notifications(desk.requester)] == ["ticket_created"]
    assert [n.type for n in facade.my_notifications(desk.technician)] == ["ticket_assigned"]
    assert facade.mark_notifications_read(desk.requester) == 1
    assert facade.my_notifications(desk.requester) == []
    assert len(facade.my_notifications(desk.technician)) == 1


def test_facade_login_returns_a_token_that_identifies_the_user(desk):
    from app.core.security import hash_password

    desk.user_repository.set_password_hash(desk.requester.id, hash_password("clave-de-prueba-123"))

    token, expires_in = desk.facade.login("sofia@school.edu", "clave-de-prueba-123")

    assert expires_in > 0
    assert desk.facade.user_from_token(token).id == desk.requester.id


def test_facade_login_fails_with_the_same_error_for_bad_credentials(desk):
    with pytest.raises(AuthenticationError):
        desk.facade.login("sofia@school.edu", "incorrecta-123")
    with pytest.raises(AuthenticationError):
        desk.facade.login("nadie@school.edu", "incorrecta-123")


def test_facade_rejects_bad_tokens_and_tokens_of_deleted_users(desk):
    with pytest.raises(AuthenticationError):
        desk.facade.user_from_token("no-es-un-token")
    with pytest.raises(AuthenticationError):
        desk.facade.user_from_token(create_access_token(9999))


class RecordingFacade:
    """22/10/2026 - Doble de la fachada: anota lo que la ruta le pide y responde sin base de datos."""

    def __init__(self):
        self.calls = []
        self.user = User(id=7, name="Rita", email="rita@school.edu", role=Role.REQUESTER)

    def user_from_token(self, token):
        self.calls.append(("user_from_token", token))
        return self.user

    def open_ticket(self, requester, *, title, description, category, priority):
        self.calls.append(("open_ticket", requester.id, title, category, priority))
        return Ticket(
            id=41,
            title=title,
            description=description,
            category=category,
            priority=priority,
            requester_id=requester.id,
        )


def test_the_create_ticket_route_only_talks_to_the_facade(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "clave-solo-para-pruebas-0123456789abcdef")
    app = create_app()
    facade = RecordingFacade()
    app.dependency_overrides[get_facade] = lambda: facade

    response = TestClient(app).post(
        "/api/tickets",
        headers={"Authorization": "Bearer token-falso"},
        json={"title": "Proyector", "description": "d", "category": "Hardware", "priority": "Low"},
    )

    assert response.status_code == 201
    assert response.json()["id"] == 41
    assert facade.calls == [
        ("user_from_token", "token-falso"),
        ("open_ticket", 7, "Proyector", "Hardware", "Low"),
    ]


# --- 3. Inyeccion de dependencias: cambio piezas con Depends, sin variables globales --


def _in_memory_services(user_repository, ticket_repository, subscriber):
    """22/10/2026 - Los mismos servicios que arma la API, pero sobre memoria y con mi suscriptor."""
    users = UserService(user_repository)
    inbox = InMemoryNotificationRepository()
    tickets = TicketService(
        ticket_repository,
        users,
        notifier=DatabaseNotifier(inbox),
        subscribers=[subscriber],
    )
    return Services(
        users=users,
        tickets=tickets,
        notifications=NotificationService(inbox),
        auth=AuthService(user_repository),
    )


def test_the_whole_api_runs_on_in_memory_pieces_through_dependency_overrides(
    user_repository, ticket_repository, monkeypatch
):
    # No hay PostgreSQL, no hay init_engine() y no hay nada global: solo reemplazo UNA dependencia.
    from app.core.security import hash_password

    monkeypatch.setenv("SECRET_KEY", "clave-solo-para-pruebas-0123456789abcdef")
    seen = []
    services = _in_memory_services(user_repository, ticket_repository, seen.append)
    sofia = services.users.register("sofia@school.edu", "Sofia", role=Role.REQUESTER)
    tomas = services.users.register("tomas@school.edu", "Tomas", role=Role.TECHNICIAN)
    user_repository.set_password_hash(sofia.id, hash_password("clave-de-prueba-123"))

    app = create_app()
    app.dependency_overrides[get_services] = lambda: services
    client = TestClient(app)

    login = client.post(
        "/api/auth/login", json={"email": "sofia@school.edu", "password": "clave-de-prueba-123"}
    )
    assert login.status_code == 200
    sofia_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    created = client.post(
        "/api/tickets",
        headers=sofia_headers,
        json={"title": "Sin red", "description": "d", "category": "Network", "priority": "Low"},
    )
    commented = client.post(
        f"/api/tickets/{created.json()['id']}/comments",
        headers={"Authorization": f"Bearer {create_access_token(tomas.id)}"},
        json={"body": "Ya voy"},
    )
    inbox = client.get("/api/notifications", headers=sofia_headers)

    assert (created.status_code, commented.status_code) == (201, 201)
    assert [type(event) for event in seen] == [TicketCreated, TicketCommented]
    assert {notice["type"] for notice in inbox.json()} == {"ticket_created", "ticket_commented"}


def test_overrides_belong_to_one_app_and_do_not_leak_to_another(
    user_repository, ticket_repository, monkeypatch
):
    monkeypatch.setenv("SECRET_KEY", "clave-solo-para-pruebas-0123456789abcdef")
    swapped = create_app()
    swapped.dependency_overrides[get_services] = lambda: _in_memory_services(
        user_repository, ticket_repository, lambda event: None
    )

    untouched = create_app()

    assert get_services in swapped.dependency_overrides
    assert untouched.dependency_overrides == {}


# --- 4. Singleton (critica): el engine lo posee la aplicacion, no el modulo ---------------
#
# ANTES: app/core/database.py guardaba `_engine` y `_session_factory` como variables
# globales del modulo. Dos aplicaciones en el mismo proceso (o dos pruebas) compartian
# el mismo engine; para cambiar de base habia que mutar el global y limpiar a mano.
# AHORA: cada create_app() crea su propio `Database` y lo cuelga de `app.state`.


def _add_probe(app):
    """22/10/2026 - Ruta de prueba: dice a que base esta conectada la sesion de la peticion."""

    @app.get("/api/_probe")
    def probe(db: DbSession):
        return {"database": db.scalar(text("SELECT current_database()"))}

    return app


def test_each_app_owns_its_own_database_object():
    url = make_url(TEST_DATABASE_URL)
    app_a = create_app(database_url=url.render_as_string(hide_password=False))
    app_b = create_app(database_url=url.set(database="postgres").render_as_string(hide_password=False))

    assert isinstance(app_a.state.database, Database)
    assert app_a.state.database is not app_b.state.database
    assert app_a.state.database.engine is not app_b.state.database.engine
    assert app_a.state.database.engine.url.database != app_b.state.database.engine.url.database


def test_two_apps_with_different_urls_do_not_share_state(pg_engine):
    url = make_url(TEST_DATABASE_URL)
    app_a = _add_probe(create_app(database_url=url.render_as_string(hide_password=False)))
    app_b = _add_probe(
        create_app(database_url=url.set(database="postgres").render_as_string(hide_password=False))
    )

    with TestClient(app_a) as client_a, TestClient(app_b) as client_b:
        first = client_a.get("/api/_probe").json()["database"]
        second = client_b.get("/api/_probe").json()["database"]
        again = client_a.get("/api/_probe").json()["database"]

    assert (first, second, again) == (url.database, "postgres", url.database)


def test_serving_requests_never_creates_the_module_level_default(pg_engine):
    database_module.dispose_engine()  # sin engine global previo
    url = make_url(TEST_DATABASE_URL).render_as_string(hide_password=False)
    app = _add_probe(create_app(database_url=url))

    with TestClient(app) as client:
        assert client.get("/api/_probe").status_code == 200

    assert database_module._default is None


def test_the_app_lifespan_disposes_its_engine_on_shutdown(pg_engine):
    url = make_url(TEST_DATABASE_URL).render_as_string(hide_password=False)
    app = create_app(database_url=url)

    with TestClient(app):
        assert app.state.database.closed is False

    assert app.state.database.closed is True


def test_database_session_scope_commits_on_success_and_rolls_back_on_error(pg_engine):
    # PRESERVE: la regla de la unidad de trabajo (semana 13) sigue igual, ahora en una instancia.
    url = make_url(TEST_DATABASE_URL).render_as_string(hide_password=False)
    database = Database(url)
    insert = text(
        "INSERT INTO users (email, name, role, password_hash) VALUES (:email, 'UoW', 'requester', 'x')"
    )
    count = text("SELECT count(*) FROM users WHERE email = :email")
    try:
        with database.session_scope() as session:
            session.execute(insert, {"email": "uow-ok@school.edu"})
        with pytest.raises(RuntimeError):
            with database.session_scope() as session:
                session.execute(insert, {"email": "uow-fail@school.edu"})
                raise RuntimeError("falla a mitad de la operacion")

        with database.session_scope() as session:
            confirmed = session.scalar(count, {"email": "uow-ok@school.edu"})
            reverted = session.scalar(count, {"email": "uow-fail@school.edu"})
            session.execute(text("DELETE FROM users WHERE email = 'uow-ok@school.edu'"))  # limpieza
    finally:
        database.dispose()

    assert (confirmed, reverted) == (1, 0)
    assert database.closed is True


def test_settings_are_read_from_the_environment_on_every_call(monkeypatch):
    # get_settings() NO es un singleton: es una funcion pura del entorno, sin estado guardado.
    from app.core.config import get_settings

    monkeypatch.setenv("APP_NAME", "Primera")
    first = get_settings().app_name
    monkeypatch.setenv("APP_NAME", "Segunda")

    assert (first, get_settings().app_name) == ("Primera", "Segunda")


# --- 5. Guardia de la base de pruebas: la base `helpdesk` de los alumnos es intocable -----
#
# Al dejar que cada app cree su propio engine, un create_app() sin URL usaria la base de
# desarrollo por defecto. La guardia obliga a que las pruebas SIEMPRE apunten a una base de
# pruebas, aunque alguien olvide pasar la URL.


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://helpdesk:helpdesk@localhost:5433/helpdesk",
        "postgresql+psycopg://helpdesk:helpdesk@localhost:5433/postgres",
        "postgresql+psycopg://helpdesk:helpdesk@localhost:5433/produccion",
    ],
)
def test_the_guard_rejects_any_database_that_is_not_a_test_database(url):
    with pytest.raises(RuntimeError, match="base de pruebas"):
        assert_is_test_database(url)


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://helpdesk:helpdesk@localhost:5433/helpdesk_test",
        "postgresql+psycopg://helpdesk:helpdesk@localhost:5433/helpdesk_test_wk14",
    ],
)
def test_the_guard_accepts_test_databases(url):
    assert_is_test_database(url)


def test_every_test_runs_with_database_url_pointing_to_a_test_database():
    # El conftest fuerza DATABASE_URL: un create_app() sin argumentos jamas toca `helpdesk`.
    import os

    assert_is_test_database(os.environ["DATABASE_URL"])
    assert make_url(os.environ["DATABASE_URL"]).database != "helpdesk"
    assert create_app().state.database.engine.url.database != "helpdesk"
