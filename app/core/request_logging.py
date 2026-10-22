"""22/10/2026 - Una linea de log por peticion HTTP (semana 17): metodo, ruta, estado y duracion.

Cuando algo falla "entre capas" (el navegador dice 401, la API dice 503, la base esta caida) lo primero
que necesito es saber QUE llego y que contesto la API. Esta linea responde eso:

    method=POST path=/api/tickets status=201 duration_ms=12.4

Lo que NUNCA escribo, a proposito:
- encabezados (ahi viaja `Authorization: Bearer <token>`);
- el cuerpo (ahi viaja la contrasena del login);
- la query string (`?token=...` es un error comun de clientes y quedaria en el log para siempre).
Solo `scope["path"]`, que no incluye la query. Es un middleware ASGI puro: no lee ni toca el cuerpo.
"""

from __future__ import annotations

import logging
from time import perf_counter

from starlette.types import ASGIApp, Message, Receive, Scope, Send

request_logger = logging.getLogger("helpdesk.request")

# 22/10/2026 - Docker consulta /api/health cada pocos segundos; en INFO taparia las lineas utiles.
QUIET_PATHS = frozenset({"/api/health"})


class RequestLogMiddleware:
    """22/10/2026 - Mide cada peticion HTTP y escribe su linea de log al terminar."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """22/10/2026 - Deja pasar lo que no es HTTP (lifespan, websockets) y mide lo que si lo es."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = perf_counter()
        status = 500  # si la ruta revienta antes de responder, eso es lo que el cliente recibe

        async def send_and_remember_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_and_remember_status)
        finally:
            duration_ms = (perf_counter() - started) * 1000
            level = logging.DEBUG if scope["path"] in QUIET_PATHS else logging.INFO
            request_logger.log(
                level,
                "method=%s path=%s status=%s duration_ms=%.1f",
                scope["method"],
                scope["path"],
                status,
                duration_ms,
            )
