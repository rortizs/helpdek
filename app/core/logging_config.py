"""22/10/2026 - Configuracion de logging de la aplicacion (semana 17).

Hasta la semana 16 `uvicorn app.main:app` no mostraba ninguna linea de `helpdesk.audit`: uvicorn solo
configura SUS loggers (`uvicorn.*`), y el modulo `logging` descarta en silencio los INFO de los demas
cuando nadie les puso un handler. Aqui le pongo uno a MI parte del arbol de loggers.

Sin sorpresas globales:
- solo toco los loggers `helpdesk` (auditoria, peticiones) y `app` (por ejemplo `app.api.errors`);
  el logger raiz y los de uvicorn, SQLAlchemy y demas bibliotecas quedan como estaban;
- es idempotente: llamarla otra vez (cada `create_app()` lo hace) reemplaza mi handler, no lo duplica;
- el nivel viene de LOG_LEVEL, nunca escrito en el codigo.
"""

from __future__ import annotations

import logging
from typing import TextIO

# 22/10/2026 - Los dos espacios de nombres de la aplicacion: `helpdesk.*` y los modulos de `app.*`.
APP_LOGGER_NAMES = ("helpdesk", "app")
LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


class _AppHandler(logging.StreamHandler):
    """22/10/2026 - Marca de mi handler: asi puedo encontrarlo y reemplazarlo sin tocar handlers ajenos."""


def configure_logging(level: str = "INFO", stream: TextIO | None = None) -> None:
    """22/10/2026 - Hace visibles los logs de la aplicacion con formato `hora NIVEL [logger] mensaje`.

    `stream` es la salida (stderr por defecto); lo recibo como parametro para poder probarla con un buffer.
    Los registros siguen propagando al logger raiz: si alguien configura uno (pytest con caplog, un agente
    de logs), tambien los recibe; uvicorn no pone handlers en la raiz, asi que en servidor no salen duplicados.
    """
    handler = _AppHandler(stream)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    for name in APP_LOGGER_NAMES:
        logger = logging.getLogger(name)
        for old in [h for h in logger.handlers if isinstance(h, _AppHandler)]:
            logger.removeHandler(old)
        logger.addHandler(handler)
        logger.setLevel(level)
