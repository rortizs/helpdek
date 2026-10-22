"""Semana 11: persistencia real con SQLAlchemy sobre PostgreSQL.

Usa la base dedicada `helpdesk_test` (ver tests/conftest.py), creada con los
scripts de docs/database: mismo esquema, mismos triggers y mismos datos semilla
que ven los alumnos. Si PostgreSQL no esta disponible, estas pruebas se omiten
(no hay respaldo en SQLite: SQLite no tiene SERIAL ni triggers y escondia bugs).
"""

from __future__ import annotations

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models.enums import Role, TicketStatus
from app.repositories.sqlalchemy import (
    CommentORM,
    HistoryEventORM,
    SqlAlchemyTicketRepository,
    SqlAlchemyUserRepository,
    TicketORM,
)
from app.services.notifications import RecordingNotifier
from app.services.tickets import TicketService
from app.services.users import UserService

# ids del seed (docs/database/seed.sql)
SEEDED_TECHNICIAN_ID = 3
SEEDED_REQUESTER_ID = 4
SEEDED_TICKET_ID = 1


def fresh_services(db):
    """Servicios nuevos sobre la misma sesion: como lo hara cada peticion web."""
    users = UserService(SqlAlchemyUserRepository(db))
    tickets = TicketService(SqlAlchemyTicketRepository(db), users, notifier=RecordingNotifier())
    return users, tickets


def test_ticket_survives_a_new_session(db):
    users, tickets = fresh_services(db)
    requester = users.register("sofia@school.edu", "Sofía Solicitante", role=Role.REQUESTER)
    created = tickets.create(
        title="Proyector dañado",
        description="No enciende",
        category="Hardware",
        priority="High",
        requester=requester,
    )
    db.commit()

    # Sesion nueva: si esto encuentra el ticket, la persistencia es real
    # (no solo un objeto vivo en memoria dentro de la misma sesion).
    with Session(db.get_bind()) as otra_sesion:
        found = SqlAlchemyTicketRepository(otra_sesion).by_id(created.id)
        assert found is not None
        assert found.title == "Proyector dañado"
        assert found.status is TicketStatus.OPEN


def test_change_status_persiste_via_update(db):
    users, tickets = fresh_services(db)
    requester = users.register("ana2@school.edu", "Ana", role=Role.REQUESTER)
    technician = users.register("luis@school.edu", "Luis", role=Role.TECHNICIAN)
    ticket = tickets.create(
        title="Sin acceso al campus",
        description="Error de credenciales",
        category="Network",
        priority="Critical",
        requester=requester,
    )
    tickets.assign(ticket.id, technician.id, actor=technician)
    tickets.change_status(ticket.id, TicketStatus.IN_PROGRESS, actor=technician)
    db.commit()

    with Session(db.get_bind()) as otra_sesion:
        found = SqlAlchemyTicketRepository(otra_sesion).by_id(ticket.id)
        assert found.status is TicketStatus.IN_PROGRESS
        assert found.assignee_id == technician.id
        # Nota: TicketService.create() en este proyecto no registra un evento
        # "created" en el historial (a diferencia de la guia de referencia);
        # eso ya esta fijado por test_week08_relations.py y se respeta aqui.
        assert [event.event_type for event in found.history] == [
            "assigned",
            "status_changed",
        ]


def test_borrar_ticket_elimina_en_cascada_comentarios_e_historial(db):
    users, tickets = fresh_services(db)
    requester = users.register("marta@school.edu", "Marta", role=Role.REQUESTER)
    ticket = tickets.create(
        title="Impresora de biblioteca",
        description="No imprime",
        category="Hardware",
        priority="Low",
        requester=requester,
    )
    tickets.comment(ticket.id, author=requester, body="Sigue sin funcionar")
    db.commit()

    db.delete(db.get(TicketORM, ticket.id))
    db.commit()

    # El seed ya trae comentarios e historial de otros tickets: se cuenta solo el de este.
    assert db.scalar(select(func.count(CommentORM.id)).where(CommentORM.ticket_id == ticket.id)) == 0
    assert db.scalar(select(func.count(HistoryEventORM.id)).where(HistoryEventORM.ticket_id == ticket.id)) == 0


# --- PostgreSQL asigna las llaves primarias --------------------------------

def test_assign_on_seeded_ticket_with_a_fresh_service(db):
    _, tickets = fresh_services(db)
    technician = fresh_services(db)[0].require(SEEDED_TECHNICIAN_ID)

    assigned = tickets.assign(SEEDED_TICKET_ID, SEEDED_TECHNICIAN_ID, actor=technician)

    stored = SqlAlchemyTicketRepository(db).by_id(SEEDED_TICKET_ID)
    assert stored.assignee_id == SEEDED_TECHNICIAN_ID
    assert [event.event_type for event in stored.history] == ["assigned"]
    assert assigned.history[-1].id == stored.history[-1].id


def test_comment_on_seeded_ticket_with_a_fresh_service(db):
    _, tickets = fresh_services(db)

    comment = tickets.comment(2, author_id=SEEDED_REQUESTER_ID, body="Sigue igual")

    stored = SqlAlchemyTicketRepository(db).by_id(2)
    # el seed trae 2 comentarios y 4 eventos en el ticket 2
    assert len(stored.comments) == 3
    assert stored.comments[-1].body == "Sigue igual"
    assert stored.comments[-1].id == comment.id
    assert len(stored.history) == 5


def test_comments_from_two_service_instances_are_both_persisted(db):
    _, first_service = fresh_services(db)
    _, second_service = fresh_services(db)

    first = first_service.comment(SEEDED_TICKET_ID, author_id=SEEDED_REQUESTER_ID, body="Primero")
    second = second_service.comment(SEEDED_TICKET_ID, author_id=SEEDED_REQUESTER_ID, body="Segundo")

    stored = SqlAlchemyTicketRepository(db).by_id(SEEDED_TICKET_ID)
    assert [comment.body for comment in stored.comments] == ["Primero", "Segundo"]
    assert first.id is not None
    assert second.id is not None
    assert first.id != second.id


def test_plain_sql_insert_after_service_inserts_gets_a_free_id(db):
    users, tickets = fresh_services(db)
    requester = users.register("nuevo@school.edu", "Nuevo", role=Role.REQUESTER)
    created = tickets.create(
        title="Teclado roto",
        description="Faltan teclas",
        category="Hardware",
        priority="Low",
        requester=requester,
    )

    # Un INSERT sin id (psql, otra aplicacion, el seed...) usa la misma secuencia.
    new_ticket_id = db.execute(
        text(
            "INSERT INTO tickets (title, description, category, priority, requester_id) "
            "VALUES ('Mouse', 'No responde', 'Hardware', 'Low', :requester_id) RETURNING id"
        ),
        {"requester_id": requester.id},
    ).scalar_one()
    new_user_id = db.execute(
        text(
            "INSERT INTO users (email, name, role, password_hash) "
            "VALUES ('otro@school.edu', 'Otro', 'requester', 'x') RETURNING id"
        )
    ).scalar_one()

    assert new_ticket_id > created.id
    assert new_user_id > requester.id


def test_repositories_write_generated_ids_back_to_domain_objects(db):
    users, tickets = fresh_services(db)
    requester = users.register("ids@school.edu", "Ids", role=Role.REQUESTER)
    ticket = tickets.create(
        title="Pantalla azul",
        description="Reinicia sola",
        category="Software",
        priority="Medium",
        requester=requester,
    )
    comment = tickets.comment(ticket.id, author=requester, body="Pasa cada hora")

    stored = tickets.require(ticket.id)

    assert requester.id is not None
    assert ticket.id is not None
    assert comment.id is not None
    assert stored.comments[0].id == comment.id
    assert stored.history[-1].id is not None
