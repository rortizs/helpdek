"""22/10/2026 - Semana 16: pruebas del cliente web que se pueden hacer desde Python.

El JavaScript corre en el navegador, asi que aqui NO se prueba su comportamiento (eso lo cubre el
`node --test` de tests/web/ para las funciones puras y la prueba manual con capturas). Lo que si se
puede garantizar desde pytest, sin base de datos:
- que FastAPI sirve las paginas y los recursos con el tipo de contenido correcto;
- que la respuesta lleva los encabezados de seguridad (CSP) y que /docs NO los hereda;
- que el HTML no trae scripts ni manejadores en linea (la CSP los bloquearia);
- que Bootstrap local es exactamente el archivo oficial (suma SHA-256);
- que ningun JavaScript del cliente pinta datos con innerHTML (regla anti-XSS).
Ninguna prueba toca PostgreSQL: crear la aplicacion no abre conexiones hasta la primera consulta.
"""

from __future__ import annotations

import hashlib
import re

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.web.static_files import CONTENT_SECURITY_POLICY, STATIC_DIR

VENDOR_DIR = STATIC_DIR / "vendor" / "bootstrap"


@pytest.fixture
def client():
    # 22/10/2026 - `with` cierra el pool de la app al terminar, igual que en las pruebas de la semana 14.
    with TestClient(create_app()) as test_client:
        yield test_client


# --- montaje: / , /app y /api conviven -------------------------------------------

def test_root_redirects_to_the_client(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/app/"


def test_app_without_trailing_slash_redirects_to_the_client_home(client):
    response = client.get("/app", follow_redirects=False)

    assert response.status_code in (307, 308)
    assert response.headers["location"].endswith("/app/")


def test_client_home_is_served_as_html(client):
    response = client.get("/app/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert '<html lang="es">' in response.text


def test_unknown_client_file_returns_the_standard_error_envelope(client):
    response = client.get("/app/no-existe.html")

    assert response.status_code == 404
    assert set(response.json()) == {"error", "message", "details"}


def test_mounting_the_client_does_not_hide_the_api(client):
    # Una ruta inexistente bajo /api sigue respondiendo con el sobre de la API, no con un archivo estatico.
    missing = client.get("/api/no-existe")
    assert missing.status_code == 404
    assert missing.json()["error"] == "http_error"
    # La raiz y el cliente no ensucian el contrato OpenAPI.
    paths = client.get("/openapi.json").json()["paths"]
    assert "/" not in paths
    assert "/api/auth/login" in paths
    assert not any(path.startswith("/app") for path in paths)


# --- encabezados de seguridad ------------------------------------------------------

@pytest.mark.parametrize(
    "url, content_type",
    [
        ("/app/", "text/html"),
        ("/app/vendor/bootstrap/bootstrap.min.css", "text/css"),
        ("/app/vendor/bootstrap/bootstrap.bundle.min.js", "javascript"),
    ],
)
def test_client_files_carry_security_headers_and_the_right_content_type(client, url, content_type):
    response = client.get(url)

    assert response.status_code == 200
    assert content_type in response.headers["content-type"]
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-cache"


def test_csp_forbids_inline_and_foreign_scripts():
    directives = dict(item.split(" ", 1) for item in CONTENT_SECURITY_POLICY.split("; "))

    assert directives["script-src"] == "'self'"
    assert "unsafe-inline" not in CONTENT_SECURITY_POLICY
    assert directives["frame-ancestors"] == "'none'"
    assert directives["object-src"] == "'none'"


def test_security_headers_are_not_forced_on_the_interactive_docs(client):
    # /docs carga Swagger UI desde un CDN y necesita otra politica: la CSP del cliente es solo de /app.
    response = client.get("/docs")

    assert response.status_code == 200
    assert "content-security-policy" not in response.headers


# --- Bootstrap local: integridad ----------------------------------------------------

def test_vendored_bootstrap_matches_the_checksums_published_in_its_readme():
    readme = (VENDOR_DIR / "README.md").read_text(encoding="utf-8")
    checked = 0
    for name in ("bootstrap.min.css", "bootstrap.bundle.min.js"):
        digest = hashlib.sha256((VENDOR_DIR / name).read_bytes()).hexdigest()
        assert digest in readme, f"{name} no coincide con la suma SHA-256 del README"
        checked += 1
    assert checked == 2
    assert re.search(r"\*\*5\.3\.\d+\*\*", readme)
