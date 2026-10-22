"""22/10/2026 - Configuracion de la aplicacion leida del entorno (semana 14).

Aqui junto todo lo que cambia entre mi maquina, la de ustedes y produccion
(URL de la base, zona horaria, vida del token) y el secreto que firma los tokens.
Nada de esto va escrito en el codigo: viene de variables de entorno.

Se lee del entorno cada vez que se pide, igual que `get_database_url()`:
asi las pruebas pueden cambiar una variable sin reiniciar el proceso.

Semana 17: se suman CORS_ORIGINS y LOG_LEVEL. Todas las variables estan documentadas en
`.env.example` y en el README; en Docker las entrega docker-compose.yml desde el archivo .env.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.core.database import get_database_url
from app.domain.clock import get_app_timezone

MIN_SECRET_LENGTH = 32
DEFAULT_TOKEN_MINUTES = 60
DEFAULT_LOG_LEVEL = "INFO"
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


# 22/10/2026 - Configuracion inmutable (frozen): nadie la cambia a mitad de una peticion.
@dataclass(frozen=True)
class Settings:
    database_url: str
    app_name: str
    debug: bool
    app_timezone: str
    access_token_minutes: int
    # 22/10/2026 - Semana 17: origenes que pueden llamar a la API desde OTRO origen (vacio = solo el mismo).
    cors_origins: tuple[str, ...]
    # 22/10/2026 - Semana 17: nivel minimo de los logs de la aplicacion (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    log_level: str


def _flag(name: str) -> bool:
    return os.environ.get(name, "false").lower() in {"1", "true", "yes"}


def _cors_origins() -> tuple[str, ...]:
    """22/10/2026 - Lee CORS_ORIGINS (origenes separados por coma) y se niega a aceptar `*`.

    Una lista explicita es la unica forma de saber quien puede llamar a mi API desde un navegador.
    Con `*` cualquier pagina de Internet podria hacerlo; por eso prefiero que la app falle al
    arrancar a que quede abierta por un descuido en el .env.
    """
    origins = tuple(o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip())
    if "*" in origins:
        raise RuntimeError(
            "CORS_ORIGINS no admite '*': escribe los origenes uno por uno, separados por coma "
            "(por ejemplo http://localhost:5500,https://helpdesk.miumg.edu)."
        )
    return origins


def _log_level() -> str:
    """22/10/2026 - Lee LOG_LEVEL en mayusculas y rechaza lo que no sea uno de los cinco niveles (un typo no debe silenciar los logs)."""
    level = os.environ.get("LOG_LEVEL", DEFAULT_LOG_LEVEL).strip().upper()
    if level not in LOG_LEVELS:
        raise RuntimeError(f"LOG_LEVEL='{level}' no es valido; usa uno de: {', '.join(LOG_LEVELS)}.")
    return level


def get_settings() -> Settings:
    """22/10/2026 - Arma la configuracion leyendo el entorno en cada llamada."""
    # SECRET_KEY no esta aqui a proposito: asi nunca aparece en un repr() ni en un log.
    return Settings(
        database_url=get_database_url(),
        app_name=os.environ.get("APP_NAME", "HelpDesk EDU"),
        debug=_flag("DEBUG"),
        app_timezone=get_app_timezone(),
        access_token_minutes=int(os.environ.get("ACCESS_TOKEN_MINUTES", DEFAULT_TOKEN_MINUTES)),
        cors_origins=_cors_origins(),
        log_level=_log_level(),
    )


def get_secret_key() -> str:
    """22/10/2026 - Clave con la que se firman los tokens. Si falta o es debil, la app NO arranca.

    Un valor por defecto "para desarrollo" terminaria en produccion tarde o
    temprano, y cualquiera que lo conozca podria fabricar tokens de administrador.
    """
    key = os.environ.get("SECRET_KEY", "")
    if len(key) < MIN_SECRET_LENGTH or key.startswith("change-me"):
        raise RuntimeError(
            "SECRET_KEY no esta definida o es debil (minimo "
            f"{MIN_SECRET_LENGTH} caracteres, y no puede ser el valor de ejemplo). "
            'Genera una con: python -c "import secrets; print(secrets.token_urlsafe(48))" '
            "y guardala en .env (uvicorn la lee con --env-file .env)."
        )
    return key
