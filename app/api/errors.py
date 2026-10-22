"""22/10/2026 - Traduce errores de dominio a respuestas HTTP con un unico formato.

Toda respuesta de error de la API tiene la misma forma, para que el cliente
(Postman, el navegador, el cliente de la semana 16) solo aprenda un formato:
    {"error": <codigo>, "message": <texto>, "details": {...}}
Los servicios lanzan errores de dominio y nunca conocen HTTP: la traduccion vive aqui.

Starlette elige el manejador por la clase del error, subiendo por la herencia:
ConflictError e InvalidStatusTransitionError heredan de ValidationError (422),
pero tienen su propio manejador (409) y por eso ganan.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.errors import (
    AuthenticationError,
    ConflictError,
    DomainError,
    InvalidStatusTransitionError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)

logger = logging.getLogger(__name__)

STATUS_BY_ERROR: dict[type[DomainError], int] = {
    AuthenticationError: 401,
    PermissionDeniedError: 403,
    NotFoundError: 404,
    InvalidStatusTransitionError: 409,
    ConflictError: 409,
    ValidationError: 422,
    DomainError: 400,
}


# 22/10/2026 - Este es el unico lugar donde construyo el JSON de error; si el formato
# cambia, cambia aqui y en ningun otro sitio.
def error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    if status_code == 401:
        headers = {**(headers or {}), "WWW-Authenticate": "Bearer"}
    return JSONResponse(
        status_code=status_code,
        content={"error": code, "message": message, "details": details},
        headers=headers,
    )


async def handle_domain_error(request: Request, error: DomainError) -> Response:
    """22/10/2026 - Convierte cualquier error de dominio en su codigo HTTP (404, 403, 409, 422...)."""
    # Se busca el primer tipo de la herencia del error que tenga status asignado.
    status_code = next(STATUS_BY_ERROR[kind] for kind in type(error).__mro__ if kind in STATUS_BY_ERROR)
    return error_response(status_code, error.code, str(error), error.properties)


async def handle_request_validation(request: Request, error: RequestValidationError) -> Response:
    """Datos de entrada mal formados (cuerpo, parametros): mismo formato que el resto."""
    errors = [
        {"field": ".".join(str(part) for part in item["loc"][1:]), "message": item["msg"]}
        for item in error.errors()
    ]
    return error_response(422, "validation_error", "the request data is invalid", {"errors": errors})


async def handle_http_exception(request: Request, error: StarletteHTTPException) -> Response:
    """Rutas inexistentes (404), metodos no permitidos (405), etc."""
    return error_response(error.status_code, "http_error", str(error.detail), {}, headers=error.headers)


async def handle_unexpected_error(request: Request, error: Exception) -> Response:
    """Cualquier otro fallo: el detalle va al log del servidor, NUNCA a la respuesta
    (podria incluir consultas SQL, rutas, direcciones de la base o contrasenas)."""
    logger.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=error)
    return error_response(500, "internal_error", "an unexpected error occurred", {})


def register_error_handlers(app: FastAPI) -> None:
    """22/10/2026 - Conecto los manejadores a la aplicacion; el orden de la herencia decide cual gana."""
    for error_class in STATUS_BY_ERROR:
        app.add_exception_handler(error_class, handle_domain_error)
    app.add_exception_handler(RequestValidationError, handle_request_validation)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unexpected_error)
