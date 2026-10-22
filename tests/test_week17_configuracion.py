"""22/10/2026 - Semana 17: configuracion por entorno, CORS y logging.

Tres preguntas que me hago antes de desplegar:
1. Todo lo que cambia entre mi maquina y produccion viene del entorno? (Settings)
2. Quien puede llamar a la API desde OTRO origen? (CORS, lista explicita y vacia por defecto)
3. Puedo ver que pasa sin filtrar secretos? (logging con formato propio y sin datos sensibles)

Ninguna de las pruebas de CORS necesita la base: el preflight lo contesta el middleware y le paso a la
app una URL inalcanzable, asi que corren aunque PostgreSQL este apagado.
"""

from __future__ import annotations

import io
import logging

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.logging_config import configure_logging
from app.main import create_app
from tests.helpers import TEST_PASSWORD

UNREACHABLE_DB = "postgresql+psycopg://helpdesk:helpdesk@localhost:5999/helpdesk_test_wk17"
ALLOWED_ORIGIN = "http://localhost:5500"
OTHER_ORIGIN = "http://evil.example"


@pytest.fixture(autouse=True)
def restore_logging():
    """22/10/2026 - Dejo los loggers de la app como estaban: ninguna prueba hereda el nivel de otra."""
    yield
    configure_logging("INFO")


# --- Settings: todo sale del entorno -------------------------------------------------


def test_settings_have_safe_defaults_for_cors_and_logging(monkeypatch):
    """22/10/2026 - Sin variables, CORS queda cerrado (solo mismo origen) y el log en INFO."""
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)

    settings = get_settings()

    assert settings.cors_origins == ()  # vacio = solo mismo origen
    assert settings.log_level == "INFO"


def test_cors_origins_are_read_from_a_comma_separated_variable(monkeypatch):
    """22/10/2026 - CORS_ORIGINS acepta varios origenes separados por coma y descarta espacios y vacios."""
    monkeypatch.setenv("CORS_ORIGINS", f" {ALLOWED_ORIGIN} , http://localhost:3000,, ")

    assert get_settings().cors_origins == (ALLOWED_ORIGIN, "http://localhost:3000")


def test_a_wildcard_origin_is_refused(monkeypatch):
    """22/10/2026 - Un `*` en CORS_ORIGINS debe impedir el arranque: prefiero fallar a quedar abierto a todo Internet."""
    monkeypatch.setenv("CORS_ORIGINS", "*")

    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        get_settings()


def test_log_level_is_case_insensitive_and_validated(monkeypatch):
    """22/10/2026 - LOG_LEVEL admite minusculas y rechaza cualquier nombre que no sea uno de los cinco niveles."""
    monkeypatch.setenv("LOG_LEVEL", "debug")
    assert get_settings().log_level == "DEBUG"

    # Solo los cinco niveles de la documentacion; alias como WARN o NOTSET (y niveles que registran otras
    # bibliotecas, como el TRACE de uvicorn) se rechazan para que el .env diga siempre lo mismo.
    for invalid in ("ruidoso", "WARN", "NOTSET", "FATAL", "TRACE"):
        monkeypatch.setenv("LOG_LEVEL", invalid)
        with pytest.raises(RuntimeError, match="LOG_LEVEL"):
            get_settings()


# --- CORS ----------------------------------------------------------------------------


def _preflight(client: TestClient, origin: str):
    """22/10/2026 - El preflight es el OPTIONS que el navegador envia antes de un fetch con Authorization."""
    return client.options(
        "/api/tickets",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )


def test_an_allowed_origin_passes_the_preflight(monkeypatch):
    """22/10/2026 - El origen de la lista recibe el preflight con su propio origen exacto, sin credenciales ni `*`."""
    monkeypatch.setenv("CORS_ORIGINS", ALLOWED_ORIGIN)

    with TestClient(create_app(database_url=UNREACHABLE_DB)) as client:
        response = _preflight(client, ALLOWED_ORIGIN)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN  # el origen exacto, nunca *
    assert "authorization" in response.headers["access-control-allow-headers"].lower()
    assert "GET" in response.headers["access-control-allow-methods"]
    assert "access-control-allow-credentials" not in response.headers  # el token va en un encabezado, no en cookies


def test_an_unknown_origin_is_rejected_by_the_preflight(monkeypatch):
    """22/10/2026 - Un origen que no esta en la lista no recibe ningun encabezado de permiso."""
    monkeypatch.setenv("CORS_ORIGINS", ALLOWED_ORIGIN)

    with TestClient(create_app(database_url=UNREACHABLE_DB)) as client:
        response = _preflight(client, OTHER_ORIGIN)

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_a_real_request_from_an_allowed_origin_can_read_the_total_count_header(monkeypatch):
    """22/10/2026 - Ademas del preflight, la respuesta real lleva el permiso y deja leer X-Total-Count al cliente de otro origen."""
    monkeypatch.setenv("CORS_ORIGINS", ALLOWED_ORIGIN)

    with TestClient(create_app(database_url=UNREACHABLE_DB)) as client:
        response = client.get("/api/health", headers={"Origin": ALLOWED_ORIGIN})

    assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
    # El cliente de la semana 16 pagina con X-Total-Count; sin expose-headers un cliente de otro origen no lo veria.
    assert "x-total-count" in response.headers["access-control-expose-headers"].lower()


def test_without_configuration_no_origin_is_allowed_and_the_client_still_works(monkeypatch):
    """22/10/2026 - Sin CORS_ORIGINS nadie de otro origen entra, y aun asi /app funciona porque es el mismo origen."""
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    with TestClient(create_app(database_url=UNREACHABLE_DB)) as client:
        preflight = _preflight(client, ALLOWED_ORIGIN)
        page = client.get("/app/")  # mismo origen: /app no necesita CORS

    assert "access-control-allow-origin" not in preflight.headers
    assert page.status_code == 200


# --- logging: configuracion --------------------------------------------------------------


def test_configure_logging_writes_time_level_logger_and_message():
    """22/10/2026 - El formato de cada linea es `hora NIVEL [logger] mensaje`, como lo explico en clase."""
    stream = io.StringIO()
    configure_logging("INFO", stream=stream)

    logging.getLogger("helpdesk.audit").info("event=ticket_created ticket=7 actor=3")

    line = stream.getvalue().strip()
    assert line.endswith("INFO [helpdesk.audit] event=ticket_created ticket=7 actor=3")
    assert line[:4].isdigit()  # empieza con la fecha del reloj (asctime)


def test_configure_logging_honours_the_level_and_does_not_duplicate_handlers():
    """22/10/2026 - El nivel manda, y configurar dos veces no repite las lineas."""
    stream = io.StringIO()
    configure_logging("WARNING", stream=stream)
    configure_logging("WARNING", stream=stream)  # llamarla dos veces no duplica lineas

    logging.getLogger("helpdesk.audit").info("esta linea no sale")
    logging.getLogger("helpdesk.audit").warning("esta linea si sale")

    assert stream.getvalue().count("esta linea si sale") == 1
    assert "esta linea no sale" not in stream.getvalue()


def test_configure_logging_does_not_touch_the_root_logger():
    """22/10/2026 - La configuracion no deja efectos globales: el logger raiz queda exactamente como estaba."""
    root_handlers = list(logging.getLogger().handlers)
    root_level = logging.getLogger().level

    configure_logging("DEBUG", stream=io.StringIO())

    assert logging.getLogger().handlers == root_handlers
    assert logging.getLogger().level == root_level


def test_create_app_applies_the_log_level_from_the_environment(monkeypatch):
    """22/10/2026 - create_app lee LOG_LEVEL del entorno y lo aplica al logger `helpdesk`."""
    monkeypatch.setenv("LOG_LEVEL", "WARNING")

    create_app(database_url=UNREACHABLE_DB)

    assert logging.getLogger("helpdesk").level == logging.WARNING


# --- logging: una linea por peticion y nada de secretos -----------------------------------


def test_every_request_logs_method_path_status_and_duration(caplog):
    """22/10/2026 - Cada peticion deja una sola linea con metodo, ruta, estado y duracion (la salud no, va en DEBUG)."""
    with TestClient(create_app(database_url=UNREACHABLE_DB)) as client:
        with caplog.at_level(logging.INFO, logger="helpdesk.request"):
            client.get("/api/health")  # la salud se registra en DEBUG (Docker la consulta cada 10 s)
            client.get("/api/tickets")  # sin token: 401

    lines = [r.getMessage() for r in caplog.records if r.name == "helpdesk.request"]
    assert len(lines) == 1
    assert lines[0].startswith("method=GET path=/api/tickets status=401 duration_ms=")
    assert float(lines[0].rsplit("=", 1)[1]) >= 0


def test_health_checks_are_logged_at_debug_only(caplog):
    """22/10/2026 - La salud se registra en DEBUG para que Docker, que la consulta cada 10 s, no tape los demas logs."""
    with TestClient(create_app(database_url=UNREACHABLE_DB)) as client:
        with caplog.at_level(logging.DEBUG, logger="helpdesk.request"):
            client.get("/api/health")

    assert any(
        r.levelno == logging.DEBUG and r.getMessage().startswith("method=GET path=/api/health status=503")
        for r in caplog.records
    )


def test_logs_never_contain_tokens_passwords_headers_or_query_strings(committed_db, caplog):
    """22/10/2026 - Prueba de seguridad del log: ni el token, ni la contrasena (buena o mala), ni encabezados, ni la query string aparecen."""
    with TestClient(create_app()) as client:
        # 22/10/2026 - Solo miro los loggers de MI aplicacion: httpx (el cliente de la prueba) registra
        # la URL completa de lo que pide, y eso no es log del servidor.
        with caplog.at_level(logging.DEBUG, logger="helpdesk"), caplog.at_level(logging.DEBUG, logger="app"):
            login = client.post(
                "/api/auth/login", json={"email": "technician@example.com", "password": TEST_PASSWORD}
            )
            token = login.json()["access_token"]
            client.post(
                "/api/auth/login", json={"email": "technician@example.com", "password": "clave-incorrecta-xyz"}
            )
            client.get(
                "/api/tickets?token=secreto-en-la-url",
                headers={"Authorization": f"Bearer {token}", "X-Api-Key": "otra-clave-secreta"},
            )

    server_log = "\n".join(
        record.getMessage() for record in caplog.records if record.name.split(".")[0] in {"helpdesk", "app"}
    )
    assert login.status_code == 200
    assert "method=POST path=/api/auth/login status=200" in server_log  # si registra, pero sin datos sensibles
    assert "method=GET path=/api/tickets status=200" in server_log
    for secret in (token, TEST_PASSWORD, "clave-incorrecta-xyz", "secreto-en-la-url", "otra-clave-secreta"):
        assert secret not in server_log
    assert "Authorization" not in server_log
    assert "Bearer" not in server_log
