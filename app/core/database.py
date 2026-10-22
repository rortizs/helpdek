"""22/10/2026 - Engine unico y unidad de trabajo (semanas 11 y 13).

Aqui concentro todo lo que tiene que ver con abrir y cerrar sesiones de base de
datos, para que ningun servicio ni repositorio tenga que decidir cuando se hace
commit.

Una "unidad de trabajo" es todo lo que se hace entre abrir una sesion y
terminarla: o se confirma completo (commit) o no queda nada (rollback).
Los repositorios NUNCA hacen commit: quien decide es `session_scope()`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.domain.clock import get_app_timezone

DEFAULT_DATABASE_URL = "postgresql+psycopg://helpdesk:helpdesk@localhost:5433/helpdesk"

# Se crean una sola vez: el engine es un pool de conexiones y es caro construirlo.
_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_database_url() -> str:
    """22/10/2026 - Se lee del entorno en cada llamada, no al importar el modulo."""
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


def create_app_engine(database_url: str) -> Engine:
    """22/10/2026 - Engine cuyas conexiones usan la zona de la aplicacion.

    CURRENT_TIMESTAMP y los triggers (due_at) calculan con la zona de la
    SESION; sin esta opcion usarian la del servidor (UTC en Docker) y las
    horas de Python y de la base quedarian desfasadas.
    """
    return create_engine(
        database_url,
        echo=False,
        connect_args={"options": f"-c timezone={get_app_timezone()}"},
    )


def init_engine(database_url: str | None = None) -> Engine:
    """22/10/2026 - Crea el engine y la fabrica de sesiones (reemplaza los anteriores)."""
    global _engine, _session_factory
    dispose_engine()
    _engine = create_app_engine(database_url or get_database_url())
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def dispose_engine() -> None:
    """22/10/2026 - Cierra el pool de conexiones (al apagar la aplicacion o entre pruebas)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def get_session_factory() -> sessionmaker[Session]:
    """22/10/2026 - Devuelve siempre la misma fabrica; el engine se crea la primera vez que se pide."""
    if _session_factory is None:
        init_engine()
    return _session_factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """22/10/2026 - Una unidad de trabajo: commit si todo sale bien, rollback si algo falla.

    Aqui es donde decido la transaccion, no en el repositorio: asi usuarios,
    tickets y avisos de una misma operacion se confirman (o se revierten) juntos.
    """
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """22/10/2026 - Igual que session_scope() pero como generador: sera una dependencia de FastAPI."""
    with session_scope() as session:
        yield session
