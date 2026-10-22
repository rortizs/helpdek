"""22/10/2026 - Semana 14: contrasenas con hash, login y tokens firmados.

Reemplaza la identidad temporal `X-User-Id` de la semana 14. Ahora el cliente
hace `POST /api/auth/login`, recibe un token firmado con vencimiento y lo envia
en cada peticion como `Authorization: Bearer <token>`.

Los usuarios del seed tienen todos la contrasena `tests.helpers.TEST_PASSWORD`
(la pone la fixture `committed_db`). Nada de esto toca la base `helpdesk`.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import statistics
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core import security
from app.core.database import session_scope
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.domain.errors import AuthenticationError
from app.main import create_app
from app.repositories.memory import InMemoryUserRepository
from app.services.auth import AuthService
from app.services.users import UserService
from app.scripts import set_password
from tests.conftest import TEST_DATABASE_URL
from tests.helpers import TEST_PASSWORD, auth_headers

REQUESTER_EMAIL = "requester@example.com"  # usuario 4
ADMIN = auth_headers(1)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def client(committed_db):
    # 22/10/2026 - Con `with`, el lifespan cierra el pool de conexiones de la app al terminar.
    with TestClient(create_app()) as test_client:
        yield test_client


def login(client, email=REQUESTER_EMAIL, password=TEST_PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def password_hash_of(email):
    with session_scope() as session:
        return session.execute(
            text("SELECT password_hash FROM users WHERE email = :email"), {"email": email}
        ).scalar_one()


# --- contrasenas: hash con sal ------------------------------------------------

def test_hash_is_not_the_password_and_verifies():
    stored = hash_password("mi-clave-segura")

    assert "mi-clave-segura" not in stored
    assert stored.startswith("scrypt$")
    assert verify_password("mi-clave-segura", stored) is True
    assert verify_password("otra-clave", stored) is False


def test_each_hash_has_its_own_salt():
    first = hash_password("misma-clave")
    second = hash_password("misma-clave")

    assert first != second  # sal distinta: dos usuarios con la misma clave no se delatan
    assert verify_password("misma-clave", first) and verify_password("misma-clave", second)


@pytest.mark.parametrize("stored", ["x", "", "scrypt$roto", "md5$1$2$3$4$5", "scrypt$a$b$c$d$e"])
def test_verify_never_raises_on_placeholder_or_malformed_hashes(stored):
    # El seed deja "x" como hash de relleno: nadie puede entrar con eso.
    assert verify_password("cualquiera", stored) is False


def test_verify_compares_in_constant_time(monkeypatch):
    calls = []
    real_compare = security.hmac.compare_digest
    monkeypatch.setattr(
        security.hmac, "compare_digest", lambda a, b: calls.append(1) or real_compare(a, b)
    )

    verify_password("clave", hash_password("clave"))

    assert calls, "la comparacion debe usar hmac.compare_digest"


# --- tokens firmados ----------------------------------------------------------

def test_token_round_trip_carries_only_the_user_id():
    token = create_access_token(4)

    assert decode_access_token(token) == 4
    claims = jwt.decode(token, options={"verify_signature": False})
    assert set(claims) == {"sub", "iat", "exp"}  # ni rol ni correo ni contrasena


def test_expired_token_is_rejected():
    token = create_access_token(4, expires_delta=timedelta(seconds=-1))

    with pytest.raises(AuthenticationError):
        decode_access_token(token)


def test_tampered_token_is_rejected():
    header, payload, signature = create_access_token(4).split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    claims["sub"] = "1"  # intento de hacerse pasar por el administrador
    forged = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")

    with pytest.raises(AuthenticationError):
        decode_access_token(f"{header}.{forged}.{signature}")


def test_token_signed_with_another_key_is_rejected():
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    forged = jwt.encode({"sub": "1", "exp": exp}, "otra-clave-" + "z" * 32, algorithm="HS256")

    with pytest.raises(AuthenticationError):
        decode_access_token(forged)


def test_unsigned_token_with_alg_none_is_rejected():
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    unsigned = jwt.encode({"sub": "1", "exp": exp}, None, algorithm="none")

    with pytest.raises(AuthenticationError):
        decode_access_token(unsigned)


@pytest.mark.filterwarnings("ignore:The HMAC key is")  # la clave de pruebas es corta para SHA-384/512
@pytest.mark.parametrize("algorithm", ["HS384", "HS512"])
def test_token_signed_with_another_algorithm_is_rejected_even_with_the_right_key(algorithm):
    # El servidor fija HS256: no acepta el algoritmo que el token diga usar.
    exp = datetime.now(timezone.utc) + timedelta(hours=1)
    other = jwt.encode({"sub": "1", "exp": exp}, os.environ["SECRET_KEY"], algorithm=algorithm)

    with pytest.raises(AuthenticationError):
        decode_access_token(other)


def test_token_without_expiry_is_rejected():
    no_expiry = jwt.encode({"sub": "1"}, os.environ["SECRET_KEY"], algorithm="HS256")

    with pytest.raises(AuthenticationError):
        decode_access_token(no_expiry)


@pytest.mark.parametrize("garbage", ["", "abc", "a.b.c", "Bearer x"])
def test_garbage_is_not_a_token(garbage):
    with pytest.raises(AuthenticationError):
        decode_access_token(garbage)


# --- SECRET_KEY: falla rapido y con un mensaje claro ---------------------------

def test_the_app_refuses_to_start_without_a_secret_key(monkeypatch):
    monkeypatch.delenv("SECRET_KEY")

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app()


@pytest.mark.parametrize("weak", ["", "corta", "change-me-" + "a" * 40])
def test_weak_or_placeholder_secrets_are_refused_without_echoing_them(monkeypatch, weak):
    monkeypatch.setenv("SECRET_KEY", weak)

    with pytest.raises(RuntimeError, match="SECRET_KEY") as error:
        create_app()

    assert weak not in str(error.value) or weak == ""


# --- POST /api/auth/login -----------------------------------------------------

def test_login_returns_a_bearer_token_that_works(client):
    response = login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    me = client.get("/api/users/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == REQUESTER_EMAIL


def test_login_normalizes_the_email(client):
    assert login(client, email="  Requester@EXAMPLE.com ").status_code == 200


def test_bad_credentials_do_not_reveal_which_part_was_wrong(client):
    wrong_password = login(client, password="incorrecta-123")
    unknown_email = login(client, email="nadie@umg.edu")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()  # mismo mensaje exacto
    assert wrong_password.json()["error"] == "unauthenticated"
    assert wrong_password.headers["www-authenticate"] == "Bearer"


def test_a_user_with_a_placeholder_hash_cannot_log_in(client):
    with session_scope() as session:
        session.execute(text("UPDATE users SET password_hash = 'x' WHERE id = 4"))

    assert login(client, password="x").status_code == 401
    assert login(client).status_code == 401


def test_placeholder_hash_user_gets_the_same_401_body_as_an_unknown_email(client):
    # Mismo estado, mismo cuerpo, mismos encabezados: la respuesta no delata al usuario del seed.
    with session_scope() as session:
        session.execute(text("UPDATE users SET password_hash = 'x' WHERE id = 4"))

    placeholder = login(client, email=REQUESTER_EMAIL, password="cualquiera-123")
    unknown = login(client, email="nadie@umg.edu", password="cualquiera-123")

    assert placeholder.status_code == unknown.status_code == 401
    assert placeholder.json() == unknown.json()
    assert placeholder.headers["www-authenticate"] == unknown.headers["www-authenticate"]


def _median_ms(authenticate, email, runs=5):
    """Mediana de `runs` intentos fallidos, en milisegundos (la mediana ignora un pico aislado)."""
    timings = []
    for _ in range(runs):
        started = time.perf_counter()
        with pytest.raises(AuthenticationError):
            authenticate(email, "clave-incorrecta-123")
        timings.append((time.perf_counter() - started) * 1000)
    return statistics.median(timings)


def test_placeholder_hash_user_costs_the_same_as_an_unknown_email():
    # Un hash ilegible (el "x" del seed) no debe contestar mucho mas rapido que un
    # correo inexistente: esa diferencia de tiempo permitiria listar los usuarios.
    repo = InMemoryUserRepository()
    UserService(repo).register("seeded@umg.edu", "Seeded")  # hash "x", como seed.sql
    auth = AuthService(repo)

    unknown = _median_ms(auth.authenticate, "nadie@umg.edu")
    placeholder = _median_ms(auth.authenticate, "seeded@umg.edu")

    # scrypt cuesta decenas de ms; sin trabajo extra el placeholder tarda ~1 ms.
    assert placeholder > unknown * 0.5, f"placeholder {placeholder:.1f} ms vs unknown {unknown:.1f} ms"


@pytest.mark.parametrize("stored", ["x", "scrypt$roto", None])
def test_verify_never_raises_for_any_string_even_a_lone_surrogate(stored):
    # "\ud800" es un str valido de Python que no se puede codificar a UTF-8 estricto.
    # None significa "un hash real": la contrasena rara tampoco debe tumbar el login.
    real_hash = hash_password("otra-clave")

    assert verify_password("\ud800", real_hash if stored is None else stored) is False


def test_authenticate_fails_cleanly_with_a_lone_surrogate_in_the_password():
    # La API ya lo corta con 422 antes de llegar aqui; el servicio se protege solo igualmente.
    repo = InMemoryUserRepository()
    users = UserService(repo)
    users.register("seeded@umg.edu", "Seeded")  # hash "x"
    real = users.register("real@umg.edu", "Real")
    repo.set_password_hash(real.id, hash_password("la-clave-real"))
    auth = AuthService(repo)

    for email in ("nadie@umg.edu", "seeded@umg.edu", "real@umg.edu"):
        with pytest.raises(AuthenticationError):
            auth.authenticate(email, "\ud800")


@pytest.mark.parametrize("stored", ["", "scrypt$roto", "md5$1$2$3$4$5", "scrypt$a$b$c$d$e"])
def test_any_unreadable_hash_spends_the_scrypt_work_too(stored):
    started = time.perf_counter()
    assert verify_password("cualquiera", stored) is False
    elapsed = (time.perf_counter() - started) * 1000

    real_hash = hash_password("otra-clave")
    started = time.perf_counter()
    assert verify_password("cualquiera", real_hash) is False
    reference = (time.perf_counter() - started) * 1000

    assert elapsed > reference * 0.5, f"{stored!r}: {elapsed:.1f} ms vs {reference:.1f} ms"


def test_login_validates_its_input(client):
    assert login(client, password="").status_code == 422
    assert login(client, password="a" * 300).status_code == 422  # evita trabajo inutil de scrypt
    assert client.post("/api/auth/login", json={"email": REQUESTER_EMAIL}).status_code == 422


def test_the_password_never_reaches_the_logs(client, caplog):
    with caplog.at_level(logging.DEBUG):
        login(client)
        login(client, password="otra-clave-incorrecta")

    assert TEST_PASSWORD not in caplog.text
    assert "otra-clave-incorrecta" not in caplog.text


def test_login_does_not_change_the_stored_hash(client):
    before = password_hash_of(REQUESTER_EMAIL)
    login(client)
    assert password_hash_of(REQUESTER_EMAIL) == before
    assert TEST_PASSWORD not in before


# --- el token es la unica identidad -------------------------------------------

@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer"},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": "Bearer basura"},
        {"X-User-Id": "1"},
    ],
)
def test_requests_without_a_valid_bearer_token_get_401(client, headers):
    response = client.get("/api/users/me", headers=headers)

    assert response.status_code == 401
    assert response.json()["error"] == "unauthenticated"
    assert response.headers["www-authenticate"] == "Bearer"


def test_x_user_id_is_ignored_even_next_to_a_valid_token(client):
    headers = {**auth_headers(4), "X-User-Id": "1"}  # el token dice 4; el encabezado, administrador

    assert client.get("/api/users/me", headers=headers).json()["id"] == 4
    assert client.get("/api/users", headers=headers).status_code == 403  # sigue siendo solicitante


def test_expired_and_tampered_tokens_get_401(client):
    expired = create_access_token(4, expires_delta=timedelta(seconds=-5))
    tampered = create_access_token(4)[:-3] + "abc"

    for token in (expired, tampered):
        response = client.get("/api/users/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401


def test_a_token_of_a_deleted_user_stops_working(client):
    with session_scope() as session:
        session.execute(text("DELETE FROM notifications WHERE user_id = 6"))
        session.execute(text("DELETE FROM history WHERE actor_id = 6"))
        session.execute(text("DELETE FROM comments WHERE author_id = 6"))
        session.execute(text("DELETE FROM articles WHERE author_id = 6"))
        session.execute(text("UPDATE tickets SET assignee_id = NULL WHERE assignee_id = 6"))
        session.execute(text("DELETE FROM users WHERE id = 6"))

    assert client.get("/api/users/me", headers=auth_headers(6)).status_code == 401


# --- usuarios nuevos con contrasena ---------------------------------------------

def test_an_administrator_can_create_a_user_who_then_logs_in(client):
    created = client.post(
        "/api/users",
        headers=ADMIN,
        json={"name": "Luis", "email": "luis@umg.edu", "password": "una-clave-larga-1"},
    )

    assert created.status_code == 201
    assert "password" not in created.json() and "password_hash" not in created.json()
    assert login(client, "luis@umg.edu", "una-clave-larga-1").status_code == 200
    assert "una-clave-larga-1" not in password_hash_of("luis@umg.edu")


def test_a_user_created_without_a_password_cannot_log_in_yet(client):
    client.post("/api/users", headers=ADMIN, json={"name": "Sin Clave", "email": "sinclave@umg.edu"})

    assert login(client, "sinclave@umg.edu", "lo-que-sea-123").status_code == 401


def test_a_too_short_password_is_422(client):
    response = client.post(
        "/api/users",
        headers=ADMIN,
        json={"name": "Luis", "email": "luis@umg.edu", "password": "corta"},
    )

    assert response.status_code == 422
    assert response.json()["details"]["errors"][0]["field"] == "password"


# --- errores inesperados: mismo sobre, sin filtrar nada ---------------------------

def test_unexpected_errors_return_the_json_envelope_without_leaking(committed_db):
    app = create_app()

    @app.get("/api/boom")
    def boom():
        raise RuntimeError("password=SuperSecreta postgresql://helpdesk:helpdesk@db/helpdesk")

    response = TestClient(app, raise_server_exceptions=False).get("/api/boom")

    assert response.status_code == 500
    body = response.json()
    assert set(body) == {"error", "message", "details"}
    assert body["error"] == "internal_error"
    assert "SuperSecreta" not in response.text and "Traceback" not in response.text
    assert "postgresql" not in response.text


def test_unknown_api_routes_use_the_envelope_too(client):
    response = client.get("/api/no-existe", headers=auth_headers(4))

    assert response.status_code == 404
    assert set(response.json()) == {"error", "message", "details"}


# --- app/scripts/set_password.py --------------------------------------------------

def test_set_password_script_changes_the_password(client):
    code = set_password.main([REQUESTER_EMAIL, "--password", "nueva-clave-segura-9"])

    assert code == 0
    assert login(client, password="nueva-clave-segura-9").status_code == 200
    assert login(client).status_code == 401  # la anterior ya no sirve


def test_set_password_prompts_twice_when_no_flag_is_given(client, monkeypatch):
    answers = iter(["clave-por-prompt-77", "clave-por-prompt-77"])
    monkeypatch.setattr(set_password.getpass, "getpass", lambda prompt="": next(answers))

    assert set_password.main([REQUESTER_EMAIL]) == 0
    assert login(client, password="clave-por-prompt-77").status_code == 200


def test_set_password_rejects_a_mismatched_confirmation(client, monkeypatch):
    answers = iter(["una-clave-larga-1", "otra-clave-larga-2"])
    monkeypatch.setattr(set_password.getpass, "getpass", lambda prompt="": next(answers))
    before = password_hash_of(REQUESTER_EMAIL)

    assert set_password.main([REQUESTER_EMAIL]) == 1
    assert password_hash_of(REQUESTER_EMAIL) == before


def test_set_password_rejects_short_passwords_and_unknown_users(client, capsys):
    before = password_hash_of(REQUESTER_EMAIL)

    assert set_password.main([REQUESTER_EMAIL, "--password", "corta"]) == 1
    assert set_password.main(["nadie@umg.edu", "--password", "una-clave-larga-1"]) == 1

    assert password_hash_of(REQUESTER_EMAIL) == before
    assert "una-clave-larga-1" not in capsys.readouterr().out  # nunca se repite la clave


def test_set_password_runs_as_a_module_against_the_database_in_the_environment(client):
    # Misma regla que conftest: cualquier base de pruebas sirve, menos la de los alumnos.
    assert make_url(TEST_DATABASE_URL).database != "helpdesk"
    result = subprocess.run(
        [sys.executable, "-m", "app.scripts.set_password", REQUESTER_EMAIL, "--password", "desde-el-modulo-55"],
        cwd=PROJECT_ROOT,
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert "desde-el-modulo-55" not in result.stdout + result.stderr
    assert login(client, password="desde-el-modulo-55").status_code == 200
