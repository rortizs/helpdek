"""22/10/2026 - Engine y unidad de trabajo (semanas 11, 13 y 15).

Una "unidad de trabajo" es todo lo que se hace entre abrir una sesion y
terminarla: o se confirma completo (commit) o no queda nada (rollback).
Los repositorios NUNCA hacen commit: quien decide es `session_scope()`.

SEMANA 15 (critica al Singleton). Hasta la semana 14 el engine y la fabrica de
sesiones eran DOS VARIABLES GLOBALES de este modulo. Eso es un Singleton: comodo,
pero con tres costos que ya nos mordieron:
  - estado global: dos aplicaciones en el mismo proceso compartian la misma base;
  - acoplamiento: cualquier modulo podia importar `session_scope()` y saltarse al dueno;
  - pruebas dificiles: para cambiar de base habia que mutar el global y limpiarlo a mano.
Ahora la clase `Database` encapsula el engine, y es la APLICACION quien la posee
(`app.state.database`, ver app/main.py). La API ya no usa ningun global.

Lo que queda del estilo anterior (init_engine, session_scope, get_session...) es un
atajo para SCRIPTS y para los ejercicios de la semana 13, que no tienen una app que
cuelgue el engine de `app.state`. Es un default perezoso y explicito (`_default`),
y la API nunca lo toca.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.domain.clock import get_app_timezone

DEFAULT_DATABASE_URL = "postgresql+psycopg://helpdesk:helpdesk@localhost:5433/helpdesk"


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


class Database:
    """22/10/2026 - Un engine (pool de conexiones) y su fabrica de sesiones, con dueno explicito.

    Crear el engine es barato (no abre conexiones hasta la primera consulta), pero
    el pool si es un recurso: quien crea la `Database` es responsable de llamar a
    `dispose()`. En la API esa responsabilidad es del lifespan de la aplicacion.
    """

    def __init__(self, database_url: str) -> None:
        self.engine: Engine = create_app_engine(database_url)
        self.session_factory: sessionmaker[Session] = sessionmaker(
            bind=self.engine, expire_on_commit=False
        )
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    @contextmanager
    def session_scope(self) -> Iterator[Session]:
        """22/10/2026 - Una unidad de trabajo: commit si todo sale bien, rollback si algo falla.

        Aqui es donde decido la transaccion, no en el repositorio: asi usuarios,
        tickets y avisos de una misma operacion se confirman (o se revierten) juntos.
        """
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        """22/10/2026 - Cierra el pool de conexiones. Se puede llamar mas de una vez."""
        self.engine.dispose()
        self._closed = True


# --- atajo para scripts y ejercicios de la semana 13 (la API NO lo usa) ----------------

# 22/10/2026 - Unico estado a nivel de modulo que me queda, y lo dejo visible a proposito.
_default: Database | None = None


def init_engine(database_url: str | None = None) -> Engine:
    """22/10/2026 - Crea (o reemplaza) la Database por defecto de los scripts."""
    global _default
    dispose_engine()
    _default = Database(database_url or get_database_url())
    return _default.engine


def dispose_engine() -> None:
    """22/10/2026 - Cierra la Database por defecto (entre pruebas o al terminar un script)."""
    global _default
    if _default is not None:
        _default.dispose()
    _default = None


def _get_default() -> Database:
    if _default is None:
        init_engine()
    return _default


def get_session_factory() -> sessionmaker[Session]:
    """22/10/2026 - Devuelve siempre la misma fabrica por defecto; el engine nace la primera vez."""
    return _get_default().session_factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """22/10/2026 - Unidad de trabajo sobre la Database por defecto (scripts y ejercicios)."""
    with _get_default().session_scope() as session:
        yield session


def get_session() -> Iterator[Session]:
    """22/10/2026 - Igual que session_scope() pero como generador (ejercicio de la semana 13)."""
    with session_scope() as session:
        yield session
