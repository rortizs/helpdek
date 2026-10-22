"""Semana 14: una sola zona horaria para toda la cadena.

Las columnas son TIMESTAMP WITHOUT TIME ZONE, asi que Python y PostgreSQL
tienen que estar de acuerdo en que hora de pared es "ahora". Ambos usan
APP_TIMEZONE (por defecto America/Guatemala), sin depender de la zona de la
maquina ni del contenedor (que suele estar en UTC).
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import session_scope
from app.domain.clock import get_app_timezone, now

GUATEMALA = ZoneInfo("America/Guatemala")
SEEDED_REQUESTER_ID = 4


def wall_clock(zone_name: str) -> datetime:
    return datetime.now(ZoneInfo(zone_name)).replace(tzinfo=None)


@pytest.fixture
def machine_zone(monkeypatch):
    """Cambia la zona del PROCESO (variable TZ) y la restaura al terminar."""
    def use(zone_name: str) -> None:
        monkeypatch.setenv("TZ", zone_name)
        time.tzset()

    yield use
    monkeypatch.undo()
    time.tzset()


# --- Python: el reloj del dominio --------------------------------------------

def test_default_timezone_is_guatemala(monkeypatch):
    monkeypatch.delenv("APP_TIMEZONE", raising=False)

    assert get_app_timezone() == "America/Guatemala"
    assert get_settings().app_timezone == "America/Guatemala"


def test_clock_matches_the_wall_time_of_the_app_timezone():
    current = now()

    assert current.tzinfo is None
    assert abs(current - wall_clock("America/Guatemala")) < timedelta(seconds=5)


@pytest.mark.parametrize("machine", ["UTC", "Asia/Tokyo", "America/New_York"])
def test_clock_does_not_depend_on_the_machine_zone(machine_zone, machine):
    machine_zone(machine)

    assert abs(now() - wall_clock("America/Guatemala")) < timedelta(seconds=5)


def test_clock_follows_app_timezone_when_it_changes(monkeypatch):
    monkeypatch.setenv("APP_TIMEZONE", "Asia/Tokyo")

    assert abs(now() - wall_clock("Asia/Tokyo")) < timedelta(seconds=5)


# --- PostgreSQL: la sesion usa la misma zona ---------------------------------

def test_app_connections_use_the_app_timezone(committed_db):
    with session_scope() as session:
        assert session.execute(text("SHOW timezone")).scalar() == "America/Guatemala"


def test_database_defaults_land_in_the_same_wall_clock_as_python(db):
    created_at = db.execute(
        text(
            "INSERT INTO comments (ticket_id, author_id, body) "
            "VALUES (1, :author, 'hora local') RETURNING created_at"
        ),
        {"author": SEEDED_REQUESTER_ID},
    ).scalar_one()

    # CURRENT_TIMESTAMP lo pone la base: tiene que coincidir con now() de Python.
    assert abs(created_at - now()) < timedelta(seconds=30)


def test_seed_rows_are_in_local_time(db):
    # seed.sql crea el ticket 1 "hace 30 horas" (SLA High: 1 dia) con CURRENT_TIMESTAMP.
    # Si la base cargara el seed en UTC, el desfase seria de 6 horas.
    created_at, due_at = db.execute(
        text("SELECT created_at, due_at FROM tickets WHERE id = 1")
    ).one()

    assert abs((now() - created_at) - timedelta(hours=30)) < timedelta(minutes=15)
    assert due_at == created_at + timedelta(days=1)
