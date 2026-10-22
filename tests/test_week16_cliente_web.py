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
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.web.static_files import CONTENT_SECURITY_POLICY, STATIC_DIR

VENDOR_DIR = STATIC_DIR / "vendor" / "bootstrap"


# 22/10/2026 - Una aplicacion nueva por prueba, con su lifespan, para que el pool se cierre al terminar.
@pytest.fixture
def client():
    # 22/10/2026 - `with` cierra el pool de la app al terminar, igual que en las pruebas de la semana 14.
    with TestClient(create_app()) as test_client:
        yield test_client


# --- montaje: / , /app y /api conviven -------------------------------------------

# 22/10/2026 - Compruebo que abrir la raiz del servidor manda al cliente web (307, temporal) y no a un 404.
def test_root_redirects_to_the_client(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/app/"


# 22/10/2026 - Compruebo que HEAD / (lo que hacen curl -I y los verificadores de salud) tambien redirige y no da 405.
def test_root_answers_head_requests_with_the_same_redirect(client):
    response = client.head("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/app/"


# 22/10/2026 - Compruebo que /app (sin barra final) tambien llega al cliente: los alumnos escriben la direccion a mano.
def test_app_without_trailing_slash_redirects_to_the_client_home(client):
    response = client.get("/app", follow_redirects=False)

    assert response.status_code in (307, 308)
    assert response.headers["location"].endswith("/app/")


# 22/10/2026 - Compruebo que /app/ entrega la pagina de ingreso como HTML en espanol.
def test_client_home_is_served_as_html(client):
    response = client.get("/app/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert '<html lang="es">' in response.text


# 22/10/2026 - Compruebo que un archivo inexistente responde 404 con el mismo sobre de error que la API (un solo formato).
def test_unknown_client_file_returns_the_standard_error_envelope(client):
    response = client.get("/app/no-existe.html")

    assert response.status_code == 404
    assert set(response.json()) == {"error", "message", "details"}


# 22/10/2026 - Compruebo que montar /app no tapo ninguna ruta de /api ni ensucio el contrato OpenAPI.
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

# 22/10/2026 - Compruebo que pagina, hoja de estilos y script llevan CSP, nosniff y el tipo de contenido correcto.
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


# 22/10/2026 - Compruebo que la politica CSP no admite scripts en linea ni de otros dominios, ni iframes ni objetos.
def test_csp_forbids_inline_and_foreign_scripts():
    directives = dict(item.split(" ", 1) for item in CONTENT_SECURITY_POLICY.split("; "))

    assert directives["script-src"] == "'self'"
    assert "unsafe-inline" not in CONTENT_SECURITY_POLICY
    assert directives["frame-ancestors"] == "'none'"
    assert directives["object-src"] == "'none'"


# 22/10/2026 - Compruebo que la CSP del cliente NO se aplica a /docs (Swagger necesita su propio CDN).
def test_security_headers_are_not_forced_on_the_interactive_docs(client):
    # /docs carga Swagger UI desde un CDN y necesita otra politica: la CSP del cliente es solo de /app.
    response = client.get("/docs")

    assert response.status_code == 200
    assert "content-security-policy" not in response.headers


# --- Bootstrap local: integridad ----------------------------------------------------

# 22/10/2026 - Compruebo que los archivos de Bootstrap son exactamente los oficiales, comparando su SHA-256 con el del README.
def test_vendored_bootstrap_matches_the_checksums_published_in_its_readme():
    readme = (VENDOR_DIR / "README.md").read_text(encoding="utf-8")
    checked = 0
    for name in ("bootstrap.min.css", "bootstrap.bundle.min.js"):
        digest = hashlib.sha256((VENDOR_DIR / name).read_bytes()).hexdigest()
        assert digest in readme, f"{name} no coincide con la suma SHA-256 del README"
        checked += 1
    assert checked == 2
    assert re.search(r"\*\*5\.3\.\d+\*\*", readme)


# --- paginas y modulos del cliente ----------------------------------------------------
# 22/10/2026 - Estas pruebas leen los archivos como texto: no ejecutan JavaScript, pero vigilan las
# reglas que mas importan (nada de scripts en linea, nada de innerHTML, comentarios de la clase).

PAGES = {
    "index.html": "js/pages/login.js",
    "tickets.html": "js/pages/tickets.js",
    "ticket-new.html": "js/pages/ticket-new.js",
    "ticket.html": "js/pages/ticket.js",
    "notifications.html": "js/pages/notifications.js",
}
JS_MODULES = sorted(path.relative_to(STATIC_DIR).as_posix() for path in (STATIC_DIR / "js").rglob("*.js"))
DATE_STAMP = "22/10/2026"


# 22/10/2026 - Quita los comentarios del JavaScript para revisar solo codigo; los comentarios SI pueden nombrar innerHTML al explicarlo.
def _strip_js_comments(source: str) -> str:
    """Quita comentarios /* */ y // para revisar solo el codigo (los comentarios pueden NOMBRAR innerHTML)."""
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return re.sub(r"(^|\s)//.*$", r"\1", source, flags=re.MULTILINE)


# 22/10/2026 - Compruebo que cada pagina se sirve y carga Bootstrap y SU modulo, nada mas.
@pytest.mark.parametrize("page", PAGES)
def test_each_page_is_served_as_html_and_loads_only_its_own_module(client, page):
    response = client.get(f"/app/{page}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert f'src="{PAGES[page]}"' in response.text
    assert 'src="vendor/bootstrap/bootstrap.bundle.min.js"' in response.text


# 22/10/2026 - Compruebo que ningun HTML trae script, estilo ni onclick en linea: la CSP los bloquearia.
@pytest.mark.parametrize("page", PAGES)
def test_pages_have_no_inline_scripts_styles_or_event_handlers(page):
    html = (STATIC_DIR / page).read_text(encoding="utf-8")

    # Todo <script> trae src: un script con cuerpo lo bloquearia la CSP.
    for tag in re.findall(r"<script\b[^>]*>(.*?)</script>", html, flags=re.DOTALL):
        assert tag.strip() == "", "script en linea"
    assert not re.search(r"<script\b(?![^>]*\bsrc=)", html), "script sin src"
    assert not re.search(r"\son[a-z]+\s*=", html, flags=re.IGNORECASE), "manejador de evento en linea"
    assert "<style" not in html and ' style="' not in html, "estilos en linea"
    assert "javascript:" not in html.lower()


# 22/10/2026 - Compruebo lo accesible que se puede ver en el HTML: idioma, viewport, enlace para saltar, h1 enfocable y region aria-live.
@pytest.mark.parametrize("page", PAGES)
def test_pages_are_accessible_by_construction(page):
    html = (STATIC_DIR / page).read_text(encoding="utf-8")

    assert '<html lang="es">' in html
    assert 'name="viewport"' in html
    assert 'class="skip-link" href="#main"' in html
    assert 'id="main"' in html
    assert re.search(r'<h1 id="page-title" tabindex="-1"[ >]', html), "el h1 recibe el foco tras navegar"
    assert 'id="alert-region"' in html and 'aria-live="assertive"' in html
    assert "<noscript>" in html


# 22/10/2026 - Compruebo que cada pagina abre con el comentario fechado del profesor (regla de la clase).
@pytest.mark.parametrize("page", PAGES)
def test_each_page_starts_with_the_dated_teacher_comment(page):
    html = (STATIC_DIR / page).read_text(encoding="utf-8")
    head = html.split("<html", 1)[0]

    assert head.lstrip().lower().startswith("<!doctype html>")
    assert re.search(rf"<!--\s*{DATE_STAMP}\b", head), "falta el comentario fechado antes de <html>"


# 22/10/2026 - Compruebo que existen todos los modulos JavaScript que el cliente necesita.
def test_every_page_has_a_module_and_every_module_belongs_to_the_client():
    expected = set(PAGES.values()) | {
        "js/api.js", "js/session.js", "js/ui.js", "js/layout.js",
        "js/format.js", "js/rules.js", "js/validation.js",
    }
    assert expected <= set(JS_MODULES)


# 22/10/2026 - Compruebo que cada modulo se sirve como JavaScript y con la CSP puesta.
@pytest.mark.parametrize("module", JS_MODULES)
def test_client_scripts_are_served_as_javascript(client, module):
    response = client.get(f"/app/{module}")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert response.headers["content-security-policy"] == CONTENT_SECURITY_POLICY


# 22/10/2026 - Regla anti-XSS: ningun modulo usa innerHTML, eval ni localStorage; los datos de la API entran con textContent.
@pytest.mark.parametrize("module", JS_MODULES)
def test_client_scripts_never_write_html_from_strings(module):
    code = _strip_js_comments((STATIC_DIR / module).read_text(encoding="utf-8"))

    # Regla de seguridad de la semana 16: los datos de la API entran al DOM con textContent o con
    # createElement, nunca como HTML. Una descripcion con <img onerror=...> no debe poder ejecutarse.
    forbidden = ["innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function", "DOMParser"]
    found = [token for token in forbidden if token in code]
    assert not found, f"{module} usa {found}"
    assert "localStorage" not in code, "el token vive en sessionStorage, no en localStorage"


# 22/10/2026 - Compruebo que cada modulo y cada funcion exportada tienen su comentario fechado de la clase.
@pytest.mark.parametrize("module", JS_MODULES)
def test_client_scripts_start_with_a_dated_header_and_comment_every_export(module):
    lines = (STATIC_DIR / module).read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("/*") and DATE_STAMP in "\n".join(lines[:4]), "falta el encabezado fechado del modulo"

    for number, line in enumerate(lines):
        if not re.match(r"export\s+(async\s+)?(function|class)\b|export\s+const\s+\w+\s*=\s*\(", line):
            continue
        block = []
        cursor = number - 1
        while cursor >= 0 and re.match(r"\s*(//|/\*|\*)", lines[cursor]):
            block.append(lines[cursor])
            cursor -= 1
        assert DATE_STAMP in "\n".join(block), f"{module}:{number + 1} export sin comentario fechado: {line.strip()}"


# 22/10/2026 - Compruebo que ningun import relativo apunta a un archivo que no existe (un error asi solo se ve en el navegador).
@pytest.mark.parametrize("module", JS_MODULES)
def test_relative_imports_resolve_to_real_files(module):
    source = (STATIC_DIR / module).read_text(encoding="utf-8")
    base = (STATIC_DIR / module).parent

    for target in re.findall(r"from\s+['\"](\.{1,2}/[^'\"]+)['\"]", source):
        assert (base / target).resolve().is_file(), f"{module} importa {target}, que no existe"


# 22/10/2026 - Compruebo que el token se guarda en sessionStorage y nunca en una cookie legible por JavaScript.
def test_the_token_is_kept_in_session_storage_only():
    session_code = _strip_js_comments((STATIC_DIR / "js/session.js").read_text(encoding="utf-8"))

    assert "sessionStorage" in session_code
    assert "document.cookie" not in session_code


# --- pruebas de JavaScript puro (Node) y reglas del repositorio ------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent


# 22/10/2026 - Ejecuta las pruebas de Node de las funciones puras del cliente (api, sesion, reglas, validacion).
@pytest.mark.skipif(shutil.which("node") is None, reason="Node no esta instalado: se omiten las pruebas de JavaScript")
def test_node_helper_tests_pass():
    # 22/10/2026 - Dejo que pytest dispare las pruebas de Node para que UNA sola orden (`uv run pytest`) cubra
    # todo lo que se puede automatizar. Sin Node se omiten; el resto del cliente se prueba igual.
    result = subprocess.run(
        ["node", "--test", "tests/web/*.test.mjs"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    assert "# fail 0" in result.stdout


# 22/10/2026 - Compruebo que los modulos Python de app/web abren con el docstring fechado.
@pytest.mark.parametrize("path", sorted(p.name for p in (STATIC_DIR.parent).glob("*.py")))
def test_python_modules_of_the_web_package_start_with_the_dated_docstring(path):
    source = (STATIC_DIR.parent / path).read_text(encoding="utf-8")

    assert source.startswith(f'"""{DATE_STAMP}'), f"{path}: el docstring debe empezar con la fecha"


# 22/10/2026 - Pregunta a git si una ruta quedaria ignorada, sin necesidad de crear el archivo.
def _is_ignored(path: str) -> bool:
    # `git check-ignore -q` devuelve 0 si la ruta esta ignorada, 1 si no, 128 si git falla.
    result = subprocess.run(["git", "check-ignore", "-q", path], cwd=REPO_ROOT, capture_output=True)
    assert result.returncode in (0, 1), result.stderr
    return result.returncode == 0


# 22/10/2026 - Compruebo que examenes, solucionarios y documentos de Office/PDF no se pueden subir por accidente a este repositorio publico.
@pytest.mark.skipif(shutil.which("git") is None, reason="git no esta instalado")
@pytest.mark.parametrize(
    "path",
    [
        "Examen_Final_Semanas_13-17.docx",
        "Solucionario_Examen_Final.pdf",
        "examen_final/estudiantes.tsv",
        "material_docente_privado/notas.txt",
        "guia.pdf",
        "presentacion.pptx",
        "hoja.xlsx",
        "carta.odt",
        "viejo.doc",
    ],
)
def test_teaching_material_is_blocked_by_gitignore(path):
    assert _is_ignored(path), f"{path} deberia estar bloqueado por .gitignore"


# 22/10/2026 - Compruebo que las reglas anteriores no ocultan el codigo, las capturas PNG ni la documentacion del proyecto.
@pytest.mark.skipif(shutil.which("git") is None, reason="git no esta instalado")
@pytest.mark.parametrize(
    "path",
    [
        "docs/img/semana16/login-1280.png",
        "docs/decisions/0006-cliente-web-semana-16.md",
        "app/web/static/index.html",
        "app/web/static/js/api.js",
        "tests/test_week16_cliente_web.py",
        "README.md",
    ],
)
def test_project_files_are_not_hidden_by_the_teaching_material_rules(path):
    assert not _is_ignored(path), f"{path} no debe quedar ignorado"
