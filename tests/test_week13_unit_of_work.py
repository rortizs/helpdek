"""Semana 13: unidad de trabajo, prioridad + due_at, notificaciones persistentes.

PRUEBAS DE ACEPTACION. Tu trabajo es escribir el codigo de `app/` para que
todas pasen; no las modifiques. Corre `uv run pytest tests/test_week13_unit_of_work.py -q`.
Necesitas PostgreSQL arriba (docker compose up -d db): sin el, estas pruebas se omiten.

Que debes construir (cada bloque de pruebas corresponde a una pieza):

1. app/core/database.py
   - `init_engine(url=None)`: crea el engine UNA sola vez (pool de conexiones).
   - `get_session_factory()`: devuelve el mismo sessionmaker siempre.
   - `session_scope()`: abre una sesion, hace commit si todo sale bien,
     rollback si hay cualquier excepcion y SIEMPRE cierra la sesion.
   - `get_session()`: lo mismo como generador (luego sera una dependencia de FastAPI).
   - `get_database_url()`: lee DATABASE_URL del entorno al llamarla.
2. app/core/services.py: `build_services(session)` -> (UserService, TicketService)
   sobre UNA misma sesion. Los repositorios nunca hacen commit.
3. app/domain/clock.py: `now()` con fecha/hora LOCAL SIN zona horaria
   (las columnas son TIMESTAMP WITHOUT TIME ZONE).
4. Ticket.due_at (lo calcula el trigger de la base) y TicketService.change_priority.
5. Notificaciones: NotificationORM + SqlAlchemyNotificationRepository
   (add, unread_for, mark_all_read) y DatabaseNotifier.
6. ConflictError cuando la base rechaza un dato duplicado.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select, text

from app.core.database import (
    get_database_url,
    get_session,
    get_session_factory,
    session_scope,
)
from app.core.services import build_services
from app.domain.clock import now
from app.domain.errors import ConflictError, PermissionDeniedError, ValidationError
from app.models.comments import Comment
from app.models.entities import HistoryEvent, Ticket, User
from app.models.enums import Role
from app.repositories.sqlalchemy import (
    CommentORM,
    HistoryEventORM,
    NotificationORM,
    SqlAlchemyNotificationRepository,
    SqlAlchemyTicketRepository,
    SqlAlchemyUserRepository,
)
from app.services.notifications import (
    DatabaseNotifier,
    NullNotifier,
    RecordingNotifier,
)

# ids del seed (docs/database/seed.sql)
SEEDED_TECHNICIAN_ID = 3
SEEDED_REQUESTER_ID = 4
SEEDED_TICKET_ID = 1


def count(db, orm_class) -> int:
    return db.scalar(select(func.count()).select_from(orm_class))


def new_ticket(tickets, requester, priority="Medium"):
    return tickets.create(
        title="Pantalla azul",
        description="Reinicia sola",
        category="Software",
        priority=priority,
        requester=requester,
    )


# --- 1. Unidad de trabajo: commit, rollback y cierre -------------------------

def test_session_scope_commits_when_the_block_succeeds(committed_db):
    with session_scope() as session:
        users, _ = build_services(session)
        users.register("nuevo@school.edu", "Nuevo", role=Role.REQUESTER)

    # Sesion distinta: solo ve el usuario si hubo commit de verdad.
    with session_scope() as otra_sesion:
        assert SqlAlchemyUserRepository(otra_sesion).by_email("nuevo@school.edu") is not None


def test_session_scope_rolls_back_when_the_block_fails(committed_db):
    with pytest.raises(RuntimeError):
        with session_scope() as session:
            users, _ = build_services(session)
            users.register("fantasma@school.edu", "Fantasma", role=Role.REQUESTER)
            raise RuntimeError("algo fallo despues de escribir")

    with session_scope() as otra_sesion:
        assert SqlAlchemyUserRepository(otra_sesion).by_email("fantasma@school.edu") is None


def test_session_scope_always_closes_the_session(committed_db):
    with session_scope() as session:
        SqlAlchemyUserRepository(session).all()
        assert session.in_transaction()
    assert not session.in_transaction()

    with pytest.raises(RuntimeError):
        with session_scope() as failing_session:
            SqlAlchemyUserRepository(failing_session).all()
            raise RuntimeError("boom")
    assert not failing_session.in_transaction()


def test_get_session_generator_commits_and_then_closes(committed_db):
    generator = get_session()
    session = next(generator)
    users, _ = build_services(session)
    users.register("generador@school.edu", "Generador", role=Role.REQUESTER)
    with pytest.raises(StopIteration):
        next(generator)  # el codigo posterior al yield hace commit y cierra
    assert not session.in_transaction()

    with session_scope() as otra_sesion:
        assert SqlAlchemyUserRepository(otra_sesion).by_email("generador@school.edu") is not None


def test_get_session_generator_rolls_back_when_the_caller_fails(committed_db):
    generator = get_session()
    session = next(generator)
    users, _ = build_services(session)
    users.register("revertido@school.edu", "Revertido", role=Role.REQUESTER)
    with pytest.raises(RuntimeError):
        generator.throw(RuntimeError("la peticion fallo"))

    with session_scope() as otra_sesion:
        assert SqlAlchemyUserRepository(otra_sesion).by_email("revertido@school.edu") is None


def test_the_engine_is_built_only_once(committed_db):
    assert get_session_factory() is get_session_factory()
    with session_scope() as first:
        first_engine = first.get_bind()
    with session_scope() as second:
        assert second.get_bind() is first_engine


def test_database_url_is_read_from_the_environment_when_called(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://otro:clave@host:1234/otra_base")
    assert get_database_url() == "postgresql+psycopg://otro:clave@host:1234/otra_base"
    monkeypatch.delenv("DATABASE_URL")
    assert get_database_url().endswith("/helpdesk")


def test_build_services_shares_one_session_between_users_and_tickets(committed_db):
    with session_scope() as session:
        users, tickets = build_services(session)
        # El usuario aun NO tiene commit: si los repositorios usaran sesiones
        # distintas, el servicio de tickets no lo veria y fallaria con UserNotFoundError.
        requester = users.register("compartida@school.edu", "Compartida", role=Role.REQUESTER)
        ticket = new_ticket(tickets, requester)
        assert ticket.id is not None

    with session_scope() as otra_sesion:
        assert SqlAlchemyTicketRepository(otra_sesion).by_id(ticket.id) is not None


# --- 2. Rollback: una operacion a medias no deja filas sueltas ---------------

class ExplodingNotifier(DatabaseNotifier):
    """Guarda la notificacion y LUEGO falla: la operacion queda a medias."""

    def notify(self, *args, **kwargs):
        super().notify(*args, **kwargs)
        raise RuntimeError("el servicio de notificaciones se cayo")


def test_a_failure_halfway_leaves_no_partial_rows(committed_db):
    with session_scope() as session:
        before = (
            count(session, CommentORM),
            count(session, HistoryEventORM),
            count(session, NotificationORM),
        )

    with pytest.raises(RuntimeError):
        with session_scope() as session:
            notifier = ExplodingNotifier(SqlAlchemyNotificationRepository(session))
            _, tickets = build_services(session, notifier=notifier)
            # Escribe el comentario, el evento de historial y la notificacion al
            # solicitante (comenta el tecnico)... y falla.
            tickets.comment(SEEDED_TICKET_ID, author_id=SEEDED_TECHNICIAN_ID, body="Revisando")

    with session_scope() as session:
        after = (
            count(session, CommentORM),
            count(session, HistoryEventORM),
            count(session, NotificationORM),
        )
    assert after == before


def test_assigning_to_a_non_technician_writes_nothing(db):
    _, tickets = build_services(db)
    before = (count(db, HistoryEventORM), count(db, NotificationORM))

    with pytest.raises(ValidationError):
        tickets.assign(SEEDED_TICKET_ID, SEEDED_REQUESTER_ID)  # el 4 es un solicitante

    assert (count(db, HistoryEventORM), count(db, NotificationORM)) == before


# --- 3. Prioridad y due_at (calculado por el trigger de la base) -------------

def test_new_ticket_gets_due_at_from_the_database_trigger(db):
    users, tickets = build_services(db)
    requester = users.register("sla@school.edu", "Sla", role=Role.REQUESTER)

    ticket = new_ticket(tickets, requester, priority="Medium")

    assert ticket.due_at == ticket.created_at + timedelta(days=2)


def test_change_priority_recalculates_due_at_in_the_database(db):
    users, tickets = build_services(db)
    requester = users.register("prio@school.edu", "Prio", role=Role.REQUESTER)
    technician = users.require(SEEDED_TECHNICIAN_ID)
    ticket = new_ticket(tickets, requester, priority="Low")
    assert ticket.due_at == ticket.created_at + timedelta(days=3)

    changed = tickets.change_priority(ticket.id, "Critical", actor=technician)

    stored_priority, stored_due_at = db.execute(
        text("SELECT priority, due_at FROM tickets WHERE id = :id"), {"id": ticket.id}
    ).one()
    assert stored_priority == "Critical"
    assert stored_due_at == ticket.created_at + timedelta(hours=4)
    assert changed.due_at == stored_due_at  # el dominio quedo sincronizado con la base


def test_change_priority_records_history(db):
    users, tickets = build_services(db)
    requester = users.register("hist@school.edu", "Hist", role=Role.REQUESTER)
    technician = users.require(SEEDED_TECHNICIAN_ID)
    ticket = new_ticket(tickets, requester, priority="Low")

    tickets.change_priority(ticket.id, "High", actor=technician)

    event = SqlAlchemyTicketRepository(db).by_id(ticket.id).history[-1]
    assert event.event_type == "priority_changed"
    assert event.actor_id == technician.id
    assert event.id is not None


def test_only_staff_can_change_priority_and_it_must_be_valid(db):
    users, tickets = build_services(db)
    requester = users.register("nostaff@school.edu", "NoStaff", role=Role.REQUESTER)
    technician = users.require(SEEDED_TECHNICIAN_ID)
    ticket = new_ticket(tickets, requester, priority="Low")

    with pytest.raises(PermissionDeniedError):
        tickets.change_priority(ticket.id, "High", actor=requester)
    with pytest.raises(ValidationError):
        tickets.change_priority(ticket.id, "Urgentisima", actor=technician)

    assert SqlAlchemyTicketRepository(db).by_id(ticket.id).priority == "Low"


def test_update_persists_title_description_and_category(db):
    users, tickets = build_services(db)
    requester = users.register("campos@school.edu", "Campos", role=Role.REQUESTER)
    ticket = new_ticket(tickets, requester)

    ticket.title = "Pantalla azul al iniciar"
    ticket.description = "Ahora reinicia al abrir el navegador"
    ticket.category = "Hardware"
    SqlAlchemyTicketRepository(db).update(ticket)

    row = db.execute(
        text("SELECT title, description, category FROM tickets WHERE id = :id"),
        {"id": ticket.id},
    ).one()
    assert tuple(row) == (
        "Pantalla azul al iniciar",
        "Ahora reinicia al abrir el navegador",
        "Hardware",
    )


# --- 4. Fechas sin zona horaria ----------------------------------------------

def test_clock_now_is_naive_local_time():
    current = now()
    assert current.tzinfo is None
    assert abs(current - datetime.now()) < timedelta(seconds=5)


def test_new_domain_objects_use_naive_timestamps():
    ticket = Ticket(title="t", description="d", category="General", priority="Low", requester_id=1)
    comment = Comment(ticket_id=1, author_id=1, body="hola")
    event = HistoryEvent(ticket_id=1, actor_id=1, event_type="x")

    for value in (ticket.created_at, ticket.updated_at, comment.created_at, event.created_at):
        assert value.tzinfo is None


def test_timestamps_are_equal_after_a_database_round_trip(db):
    users, tickets = build_services(db)
    requester = users.register("fechas@school.edu", "Fechas", role=Role.REQUESTER)
    technician = users.require(SEEDED_TECHNICIAN_ID)
    created = new_ticket(tickets, requester)
    comment = tickets.comment(created.id, author=requester, body="Pasa cada hora")
    # change_priority devuelve el ticket con TODO lo que acabamos de escribir.
    written = tickets.change_priority(created.id, "High", actor=technician)

    db.expire_all()  # obliga a releer las filas desde PostgreSQL
    stored = SqlAlchemyTicketRepository(db).by_id(created.id)

    assert stored.created_at == created.created_at
    assert stored.updated_at == written.updated_at
    assert stored.comments[0].created_at == comment.created_at
    assert [event.created_at for event in stored.history] == [
        event.created_at for event in written.history
    ]


# --- 5. Notificaciones persistentes ------------------------------------------

def test_database_notifier_stores_the_notification_in_the_same_session(db):
    _, tickets = build_services(db)
    notifications = SqlAlchemyNotificationRepository(db)
    assert notifications.unread_for(SEEDED_TECHNICIAN_ID) == []

    tickets.assign(SEEDED_TICKET_ID, SEEDED_TECHNICIAN_ID)

    (stored,) = notifications.unread_for(SEEDED_TECHNICIAN_ID)
    assert stored.id is not None
    assert stored.ticket_id == SEEDED_TICKET_ID
    assert stored.type == "ticket_assigned"
    assert stored.title == "Ticket asignado"  # titulo legible, no el codigo
    assert stored.message == f"Ticket #{SEEDED_TICKET_ID} was assigned to you"
    assert stored.read_at is None


def test_creating_a_ticket_notifies_the_requester(db):
    users, tickets = build_services(db)
    requester = users.register("aviso@school.edu", "Aviso", role=Role.REQUESTER)

    ticket = new_ticket(tickets, requester)

    (stored,) = SqlAlchemyNotificationRepository(db).unread_for(requester.id)
    assert (stored.type, stored.ticket_id) == ("ticket_created", ticket.id)


def test_mark_all_read_returns_how_many_and_empties_the_inbox(db):
    notifications = SqlAlchemyNotificationRepository(db)
    unread = len(notifications.unread_for(SEEDED_REQUESTER_ID))
    assert unread >= 1  # el seed deja avisos sin leer para el usuario 4

    assert notifications.mark_all_read(SEEDED_REQUESTER_ID) == unread
    assert notifications.unread_for(SEEDED_REQUESTER_ID) == []
    assert notifications.mark_all_read(SEEDED_REQUESTER_ID) == 0


def test_notifier_interface_stays_backward_compatible(world):
    # Los notificadores de las semanas 7-9 se siguen usando con tres argumentos...
    NullNotifier().notify(1, "titulo", "mensaje")
    recording = RecordingNotifier()
    recording.notify(1, "titulo", "mensaje")
    assert recording.sent[-1].ticket_id is None

    # ...y ahora ademas reciben el ticket al que se refiere el aviso.
    ticket = world.tickets.create(
        title="Sin internet",
        description="Aula 3",
        category="Network",
        priority="High",
        requester=world.requester,
    )
    assert world.notifier.sent[-1].ticket_id == ticket.id


# --- 6. Errores de la base -> errores de dominio -----------------------------

def test_duplicate_email_becomes_a_conflict_error(db):
    repository = SqlAlchemyUserRepository(db)

    with pytest.raises(ConflictError) as error:
        repository.add(User(name="Otra Ana", email="ana@umg.edu"))  # ya existe en el seed

    assert isinstance(error.value, ValidationError)  # los manejadores existentes lo entienden
    assert error.value.properties["field"] == "email"
    # La sesion sigue usable despues del error (el INSERT fallido no la dejo rota).
    assert repository.by_email("ana@umg.edu") is not None
