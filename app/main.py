"""22/10/2026 - Punto de entrada: la API JSON bajo /api (semana 14).

Aqui armo la aplicacion FastAPI: registro los routers, los manejadores de error
y exijo SECRET_KEY antes de aceptar trafico. La documentacion OpenAPI sale
sola en /docs y /openapi.json a partir de las rutas y los esquemas.

    uv run uvicorn app.main:app --reload --env-file .env
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from app.api.errors import register_error_handlers
from app.api.routes import auth, notifications, system, tickets, users
from app.core.config import get_secret_key, get_settings
from app.core.database import Database


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """22/10/2026 - Al apagar la aplicacion cierro SU pool de conexiones (el que ella creo)."""
    yield
    app.state.database.dispose()


def create_app(database_url: str | None = None) -> FastAPI:
    """22/10/2026 - Fabrica de la aplicacion: las pruebas crean una nueva por cada caso.

    Semana 15: cada aplicacion crea y posee su `Database` (engine + sesiones) y la
    cuelga de `app.state`. Dos aplicaciones con URLs distintas no comparten nada.
    """
    get_secret_key()  # falla rapido y claro si falta SECRET_KEY, antes de aceptar trafico
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", debug=settings.debug, lifespan=lifespan)
    app.state.database = Database(database_url or settings.database_url)

    api = APIRouter(prefix="/api")
    api.include_router(system.router)
    api.include_router(auth.router)
    api.include_router(tickets.router)
    api.include_router(users.router)
    api.include_router(notifications.router)
    app.include_router(api)

    register_error_handlers(app)
    return app


app = create_app()
