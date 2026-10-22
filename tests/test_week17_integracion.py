"""22/10/2026 - Semana 17: prueba de integracion de punta a punta (cliente HTTP -> API -> servicios -> PostgreSQL).

Las pruebas unitarias de las semanas anteriores miran UNA capa con las demas reemplazadas. Esta recorre todas las
capas juntas, sin reemplazar nada: lo mismo que hace el cliente web de la semana 16, pero desde Python. Si una capa
se descuadra con otra (un esquema, un permiso, un trigger), aqui es donde se nota.

Se ejecuta contra la base `helpdesk_test` (fixture `committed_db`: confirma de verdad y reinicia con el seed).
Corre aparte de las unitarias con el marcador `integration`:

    uv run pytest -m "not integration"     # unitarias: rapidas, sin PostgreSQL
    uv run pytest -m integration           # integracion: necesitan PostgreSQL en TEST_DATABASE_URL
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.helpers import TEST_PASSWORD

pytestmark = pytest.mark.integration

NEW_TICKET = {
    "title": "Sin red en A101",
    "description": "El aula no tiene internet desde la manana",
    "category": "Network",
    "priority": "High",
}


def _login(client: TestClient, email: str) -> dict[str, str]:
    """22/10/2026 - Ingreso por la API como lo hace el cliente web: correo + contrasena -> token Bearer."""
    response = client.post("/api/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_a_ticket_goes_from_creation_to_resolution_through_every_layer(committed_db, caplog):
    with TestClient(create_app()) as client, caplog.at_level(logging.INFO, logger="helpdesk"):
        assert client.get("/api/health").json() == {"status": "ok"}  # la API ve la base
        requester = _login(client, "requester@example.com")
        technician = _login(client, "technician@example.com")
        technician_id = client.get("/api/users/me", headers=technician).json()["id"]

        created = client.post("/api/tickets", headers=requester, json=NEW_TICKET)
        ticket_id = created.json()["id"]
        assigned = client.post(f"/api/tickets/{ticket_id}/assign", headers=technician, json={"technician_id": technician_id})
        started = client.patch(f"/api/tickets/{ticket_id}/status", headers=technician, json={"status": "in_progress"})
        commented = client.post(f"/api/tickets/{ticket_id}/comments", headers=technician, json={"body": "Revisando el switch"})
        resolved = client.patch(f"/api/tickets/{ticket_id}/status", headers=technician, json={"status": "resolved"})

        notices = client.get("/api/notifications", headers=requester).json()
        detail = client.get(f"/api/tickets/{ticket_id}", headers=requester).json()

    assert [r.status_code for r in (created, assigned, started, commented, resolved)] == [201, 200, 200, 201, 200]
    assert detail["status"] == "resolved"
    assert detail["assignee_id"] == technician_id
    assert [c["body"] for c in detail["comments"]] == ["Revisando el switch"]
    # El solicitante se entera de todo lo que paso con SU ticket, sin que el tecnico tenga que avisarle.
    assert {n["type"] for n in notices if n["ticket_id"] == ticket_id} >= {
        "ticket_created",
        "ticket_commented",
        "ticket_status_changed",
    }
    # La auditoria (Observer de la semana 15) y las peticiones (semana 17) quedaron en el log, ya visibles.
    audit = [r.getMessage() for r in caplog.records if r.name == "helpdesk.audit"]
    assert f"event=ticket_created ticket={ticket_id} actor=4" in audit
    assert any(f"ticket={ticket_id}" in line and line.startswith("event=ticket_status_changed") for line in audit)
    requests = [r.getMessage() for r in caplog.records if r.name == "helpdesk.request"]
    assert any(line.startswith("method=POST path=/api/tickets status=201") for line in requests)


def test_what_one_process_confirms_another_process_can_read(committed_db):
    # Dos aplicaciones = dos pools de conexiones distintos (como dos reinicios del servidor): si el dato se ve
    # desde la segunda, de verdad llego a PostgreSQL y no se quedo en la memoria de la primera.
    with TestClient(create_app()) as first:
        ticket_id = first.post("/api/tickets", headers=_login(first, "requester@example.com"), json=NEW_TICKET).json()["id"]

    with TestClient(create_app()) as second:
        found = second.get(f"/api/tickets/{ticket_id}", headers=_login(second, "requester@example.com"))

    assert found.status_code == 200
    assert found.json()["title"] == NEW_TICKET["title"]


def test_a_requester_cannot_reach_another_requesters_ticket(committed_db):
    with TestClient(create_app()) as client:
        created = client.post("/api/tickets", headers=_login(client, "requester@example.com"), json=NEW_TICKET)

        other = client.get(f"/api/tickets/{created.json()['id']}", headers=_login(client, "ana@umg.edu"))

    assert other.status_code == 404
    assert other.json()["error"] == "ticket_not_found"  # no se revela ni que el ticket existe


def test_the_web_client_and_the_api_are_served_by_the_same_process(committed_db):
    with TestClient(create_app()) as client:
        page = client.get("/app/")
        login_script = client.get("/app/js/pages/login.js")
        api = client.get("/api/tickets")

    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    assert login_script.status_code == 200
    assert "content-security-policy" in page.headers
    assert api.status_code == 401  # la API sigue pidiendo token aunque el cliente sea publico
