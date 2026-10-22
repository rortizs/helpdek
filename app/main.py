"""22/10/2026 - Punto de entrada: la API JSON bajo /api (semana 14) y el cliente web bajo /app (semana 16).

Aqui armo la aplicacion FastAPI: registro los routers, los manejadores de error
y exijo SECRET_KEY antes de aceptar trafico. La documentacion OpenAPI sale
sola en /docs y /openapi.json a partir de las rutas y los esquemas.

Semana 16: el mismo proceso sirve el cliente web (HTML, CSS y JavaScript) en /app. Un solo origen
significa que el navegador no necesita CORS para llamar a /api.

Semana 17: CORS con lista explicita de origenes (CORS_ORIGINS), logging configurado desde LOG_LEVEL y una
linea de log por peticion. Con Docker: `docker compose up -d --build` y abrir http://localhost:8000/app.

    uv run uvicorn app.main:app --reload --env-file .env
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.api.errors import register_error_handlers
from app.api.routes import auth, notifications, system, tickets, users
from app.core.config import get_secret_key, get_settings
from app.core.database import Database
from app.core.logging_config import configure_logging
from app.core.request_logging import RequestLogMiddleware
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


def add_cors(app: FastAPI, origins: tuple[str, ...]) -> None:
    """22/10/2026 - Semana 17: abre CORS SOLO para los origenes de la lista; sin lista no instala nada.

    Por que /app NO lo necesita: el navegador compara el ORIGEN (esquema + host + puerto) de la pagina con el de
    la API. /app y /api salen del mismo servidor (http://localhost:8000), asi que son el mismo origen y no hay
    nada que permitir. Cuando SI hace falta: si el cliente se sirve desde otro origen, por ejemplo
    `python -m http.server 5500` (http://localhost:5500) llamando a la API en el 8000; el navegador manda un
    preflight (OPTIONS) y bloquea la respuesta si la API no lo autoriza. Entonces se agrega ese origen a CORS_ORIGINS.

    - allow_origins es la lista exacta: nunca `*` (config.py ya lo rechaza).
    - allow_credentials=False: el token viaja en el encabezado Authorization, no en cookies, asi que no hay
      credenciales del navegador que proteger; asi tampoco puede combinarse con un origen abierto.
    - expose_headers: el cliente pagina con `X-Total-Count`, y un cliente de otro origen no puede leerlo si no se expone.
    """
    if not origins:
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Total-Count"],
        allow_credentials=False,
        max_age=600,
    )


def create_app(database_url: str | None = None) -> FastAPI:
    """22/10/2026 - Fabrica de la aplicacion: las pruebas crean una nueva por cada caso.

    Semana 15: cada aplicacion crea y posee su `Database` (engine + sesiones) y la
    cuelga de `app.state`. Dos aplicaciones con URLs distintas no comparten nada.

    Semana 17: tambien configura los logs (LOG_LEVEL), abre CORS solo para los origenes de
    CORS_ORIGINS y agrega el middleware que escribe una linea de log por peticion.
    """
    get_secret_key()  # falla rapido y claro si falta SECRET_KEY, antes de aceptar trafico
    settings = get_settings()
    configure_logging(settings.log_level)  # semana 17: hace visibles helpdesk.audit y helpdesk.request
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
    app.add_api_route("/", redirect_to_client, methods=["GET", "HEAD"], include_in_schema=False)

    register_error_handlers(app)
    # 22/10/2026 - Semana 17: el ULTIMO middleware agregado es el mas externo. CORS va primero (mas adentro)
    # y el log de peticiones despues, para que tambien registre los preflight y los rechazos de CORS.
    add_cors(app, settings.cors_origins)
    app.add_middleware(RequestLogMiddleware)
    return app


app = create_app()
