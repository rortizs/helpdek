"""22/10/2026 - Punto de entrada: la API JSON bajo /api (semana 14) y el cliente web bajo /app (semana 16).

Aqui armo la aplicacion FastAPI: registro los routers, los manejadores de error
y exijo SECRET_KEY antes de aceptar trafico. La documentacion OpenAPI sale
sola en /docs y /openapi.json a partir de las rutas y los esquemas.

Semana 16: el mismo proceso sirve el cliente web (HTML, CSS y JavaScript) en /app. Un solo origen
significa que el navegador no necesita CORS para llamar a /api; en la semana 17 se explica cuando si.

    uv run uvicorn app.main:app --reload --env-file .env
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.responses import RedirectResponse

from app.api.errors import register_error_handlers
from app.api.routes import auth, notifications, system, tickets, users
from app.core.config import get_secret_key, get_settings
from app.core.database import Database
from app.web.static_files import STATIC_DIR, ClientStaticFiles


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """22/10/2026 - Al apagar la aplicacion cierro SU pool de conexiones (el que ella creo)."""
    yield
    app.state.database.dispose()


def redirect_to_client() -> RedirectResponse:
    """22/10/2026 - GET /: quien abre la raiz del servidor en el navegador cae en el cliente web.

    Uso 307 (redireccion temporal) y no 301: si algun dia la raiz sirve otra cosa, ningun
    navegador se quedo recordando para siempre este destino.
    """
    return RedirectResponse("/app/", status_code=307)


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

    # 22/10/2026 - Semana 16: monto el cliente web DESPUES de /api para que ninguna ruta de la
    # API quede tapada. html=True hace que /app/ entregue index.html (la pagina de ingreso).
    app.mount("/app", ClientStaticFiles(directory=STATIC_DIR, html=True), name="web")
    app.add_api_route("/", redirect_to_client, include_in_schema=False)

    register_error_handlers(app)
    return app


app = create_app()
