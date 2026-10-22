"""22/10/2026 - Configuracion de la aplicacion leida del entorno (semana 14).

Aqui junto todo lo que cambia entre mi maquina, la de ustedes y produccion
(URL de la base, zona horaria, vida del token) y el secreto que firma los tokens.
Nada de esto va escrito en el codigo: viene de variables de entorno.

Se lee del entorno cada vez que se pide, igual que `get_database_url()`:
asi las pruebas pueden cambiar una variable sin reiniciar el proceso.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.core.database import get_database_url
from app.domain.clock import get_app_timezone

MIN_SECRET_LENGTH = 32
DEFAULT_TOKEN_MINUTES = 60


# 22/10/2026 - Configuracion inmutable (frozen): nadie la cambia a mitad de una peticion.
@dataclass(frozen=True)
class Settings:
    database_url: str
    app_name: str
    debug: bool
    app_timezone: str
    access_token_minutes: int


def _flag(name: str) -> bool:
    return os.environ.get(name, "false").lower() in {"1", "true", "yes"}


def get_settings() -> Settings:
    """22/10/2026 - Arma la configuracion leyendo el entorno en cada llamada."""
    # SECRET_KEY no esta aqui a proposito: asi nunca aparece en un repr() ni en un log.
    return Settings(
        database_url=get_database_url(),
        app_name=os.environ.get("APP_NAME", "HelpDesk EDU"),
        debug=_flag("DEBUG"),
        app_timezone=get_app_timezone(),
        access_token_minutes=int(os.environ.get("ACCESS_TOKEN_MINUTES", DEFAULT_TOKEN_MINUTES)),
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
