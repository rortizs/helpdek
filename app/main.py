"""22/10/2026 - Punto de entrada: la API JSON bajo /api (semana 14).

Aqui armo la aplicacion FastAPI: registro los routers, los manejadores de error
y exijo SECRET_KEY antes de aceptar trafico. La documentacion OpenAPI sale
sola en /docs y /openapi.json a partir de las rutas y los esquemas.

    uv run uvicorn app.main:app --reload --env-file .env
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI

from app.api.errors import register_error_handlers
from app.api.routes import auth, notifications, system, tickets, users
from app.core.config import get_secret_key, get_settings


def create_app() -> FastAPI:
    """22/10/2026 - Fabrica de la aplicacion: las pruebas crean una nueva por cada caso."""
    get_secret_key()  # falla rapido y claro si falta SECRET_KEY, antes de aceptar trafico
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", debug=settings.debug)

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
