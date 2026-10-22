"""22/10/2026 - Reloj unico del dominio.

Las columnas son TIMESTAMP WITHOUT TIME ZONE: guardan fecha y hora sin zona.
Si el dominio usara fechas con zona (aware), el valor que sale de la base
(naive) no seria igual al que entro. Por eso todo el dominio usa hora local
sin zona, y solo se obtiene de aqui.

"Local" significa la zona de la aplicacion (APP_TIMEZONE), NO la de la maquina:
un servidor o contenedor en UTC daria otra hora de pared. PostgreSQL usa la
misma zona en cada conexion (ver app/core/database.py).
"""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT_TIMEZONE = "America/Guatemala"


def get_app_timezone() -> str:
    """22/10/2026 - Zona de toda la aplicacion; se lee del entorno en cada llamada."""
    return os.environ.get("APP_TIMEZONE", DEFAULT_TIMEZONE)


def now() -> datetime:
    """22/10/2026 - Hora de pared de America/Guatemala SIN zona, lista para guardar en TIMESTAMP."""
    return datetime.now(ZoneInfo(get_app_timezone())).replace(tzinfo=None)
