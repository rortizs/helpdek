"""22/10/2026 - Fixtures compartidas.

Aqui dejo dos mundos de prueba: servicios sobre repositorios en memoria (rapidos,
sin base) y sesiones sobre PostgreSQL real, siempre contra `helpdesk_test`.
La base `helpdesk` guarda la practica de los alumnos y nunca se toca desde aqui.
"""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

# Las pruebas firman tokens con su propia clave; la aplicacion real EXIGE SECRET_KEY.
os.environ.setdefault("SECRET_KEY", "clave-solo-para-pruebas-0123456789abcdef")

from app.core.database import create_app_engine, dispose_engine, init_engine
from app.models.enums import Role
from app.repositories.memory import InMemoryTicketRepository, InMemoryUserRepository
from app.services.notifications import RecordingNotifier
from app.services.tickets import TicketService
from app.services.users import UserService
from tests.helpers import assert_is_test_database, seeded_password_hashes


# 22/10/2026 - Semana 17: las fixtures que abren PostgreSQL real. Una prueba que use cualquiera de ellas es de
# INTEGRACION; asi `pytest -m "not integration"` corre sin base de datos y nadie tiene que acordarse de marcar a mano.
DATABASE_FIXTURES = frozenset({"pg_engine", "db", "committed_db"})


def pytest_collection_modifyitems(items):
    """22/10/2026 - Agrega el marcador `integration` a toda prueba que dependa de una fixture con base de datos."""
    for item in items:
        if DATABASE_FIXTURES & set(item.fixturenames):
            item.add_marker(pytest.mark.integration)


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


# --- PostgreSQL real para las pruebas de integracion (semana 11) -------------
# Una base DEDICADA (`helpdesk_test`) que se recrea una vez por sesion de pytest
# con los mismos scripts que usa el curso. Nunca se toca la base `helpdesk`,
# que guarda los datos de practica de los alumnos.

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://helpdesk:helpdesk@localhost:5433/helpdesk_test",
)
# 22/10/2026 - Guardia de la semana 15. Cada app crea ahora su propio engine desde
# DATABASE_URL; si una prueba olvidara pasar la URL, usaria la base `helpdesk` de los
# alumnos y la contaminaria. Por eso (1) rechazo cualquier TEST_DATABASE_URL que no sea
# una base de pruebas y (2) FUERZO DATABASE_URL a la base de pruebas durante toda la sesion.
assert_is_test_database(TEST_DATABASE_URL)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

SQL_SCRIPTS = ("database.sql", "functions_triggers.sql", "seed.sql")
SQL_DIR = Path(__file__).resolve().parent.parent / "docs" / "database"


def _recreate_test_database(url) -> None:
    """Borra y crea la base de pruebas desde una conexion admin a `postgres`."""
    admin_engine = create_engine(
        url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    with admin_engine.connect() as admin:
        admin.exec_driver_sql(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)')
        admin.exec_driver_sql(f'CREATE DATABASE "{url.database}"')
    admin_engine.dispose()


def _load_scripts(engine, scripts=SQL_SCRIPTS) -> None:
    """Ejecuta cada script completo (sin parametros) en el orden del curso."""
    raw = engine.raw_connection()
    try:
        for name in scripts:
            raw.cursor().execute((SQL_DIR / name).read_text(encoding="utf-8"))
        raw.commit()
    finally:
        raw.close()


@pytest.fixture(scope="session")
def pg_engine():
    # 22/10/2026 - Recreo `helpdesk_test` una vez por sesion desde docs/database y me
    # niego a correr si alguien apunta TEST_DATABASE_URL a la base real.
    url = make_url(TEST_DATABASE_URL)
    if url.database == "helpdesk":
        raise RuntimeError("TEST_DATABASE_URL no puede apuntar a la base `helpdesk`")
    try:
        _recreate_test_database(url)
    except OperationalError:
        pytest.skip(f"PostgreSQL no disponible en {url.render_as_string()}")

    # Misma zona que la aplicacion: el seed (CURRENT_TIMESTAMP) queda en hora local.
    engine = create_app_engine(url)
    _load_scripts(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(pg_engine):
    """Sesion por prueba: todo lo escrito (incluso con commit) se revierte al final."""
    connection = pg_engine.connect()
    outer = connection.begin()
    session = Session(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    yield session
    session.close()
    outer.rollback()
    connection.close()


@pytest.fixture
def committed_db(pg_engine):
    """22/10/2026 - Esta fixture SI confirma: la uso para probar commit y rollback reales.

    Para probar commit/rollback REALES (semana 13).

    `db` nunca confirma nada: lo revierte todo al final. Aqui `session_scope()`
    si hace commit, asi que antes y despues de cada prueba se vacian las tablas
    y se vuelve a cargar el seed (los ids vuelven a empezar en 1).
    """
    def reset() -> None:
        with pg_engine.begin() as connection:
            connection.exec_driver_sql(
                "TRUNCATE users, tickets, comments, history, notifications, articles "
                "RESTART IDENTITY CASCADE"
            )
        _load_scripts(pg_engine, scripts=("seed.sql",))
        # El seed trae hashes de relleno; aqui todos los usuarios reciben una
        # contrasena conocida (tests.helpers.TEST_PASSWORD) para probar el login.
        with pg_engine.begin() as connection:
            for user_id, password_hash in seeded_password_hashes().items():
                connection.execute(
                    text("UPDATE users SET password_hash = :hash WHERE id = :id"),
                    {"hash": password_hash, "id": user_id},
                )

    reset()
    init_engine(TEST_DATABASE_URL)
    yield
    dispose_engine()
    reset()
