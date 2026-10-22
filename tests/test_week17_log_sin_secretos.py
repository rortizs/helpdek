"""22/10/2026 - Regresion de la semana 17: el log de peticiones nunca guarda secretos.

Lo agrego despues de la verificacion independiente: pruebo de punta a punta que ni el
token en la URL, ni el encabezado Authorization, ni la contrasena de la base aparecen en
el log, aunque la peticion falle porque la base no responde.
"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient

from app.core.logging_config import configure_logging
from app.main import create_app


def test_request_log_never_contains_query_or_authorization(monkeypatch):
    # 22/10/2026 - Apunto a una base inalcanzable a proposito: /api/health responde 503 y aun asi
    # el log solo debe tener metodo, ruta, estado y duracion.
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:SuperPw@localhost:1/x_test")
    app = create_app()
    buffer = io.StringIO()
    configure_logging("DEBUG", buffer)
    client = TestClient(app, raise_server_exceptions=False)
    client.get("/api/health?token=LEAKTOKEN", headers={"Authorization": "Bearer LEAKBEARER"})
    log = buffer.getvalue()
    assert "path=/api/health status=503" in log
    assert not any(secret in log for secret in ("LEAKTOKEN", "LEAKBEARER", "SuperPw"))
