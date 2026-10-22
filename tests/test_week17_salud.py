"""22/10/2026 - Semana 17: GET /api/health cuando la base se cae con conexiones ya abiertas.

El caso real de produccion: el contenedor de PostgreSQL se reinicia y el pool de la
aplicacion todavia guarda conexiones que ya murieron. Hasta la semana 16 la PRIMERA
peticion de salud despues de la caida respondia 500 (y recien la segunda 503), justo
cuando mas necesito un diagnostico claro. Esta prueba reproduce esa caida matando, desde
el servidor, la conexion que el pool de la aplicacion tiene guardada.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import create_app


def _kill_pooled_connection(app, pg_engine) -> None:
    """22/10/2026 - Termina en el servidor la conexion que el pool de la app dejo guardada.

    Primero hago una consulta con el engine de la aplicacion para saber el pid de su conexion
    y la devuelvo al pool; luego, desde otra conexion, la mato con pg_terminate_backend. Asi el
    pool cree que la conexion sigue viva (no hay pre_ping) y la entrega rota a la peticion.
    """
    with app.state.database.engine.connect() as connection:
        pid = connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
    with pg_engine.connect() as admin:
        admin.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})


def test_health_answers_503_on_the_first_request_after_the_database_drops_connections(committed_db, pg_engine):
    """22/10/2026 - Esta es la prueba del error: la primera salud tras matar la conexion del pool debe ser 503 y no 500."""
    app = create_app()
    # raise_server_exceptions=False: si la ruta revienta quiero VER el 500, no una excepcion de la prueba.
    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/api/health").status_code == 200  # el pool guarda una conexion buena
        _kill_pooled_connection(app, pg_engine)

        first = client.get("/api/health")

    assert first.status_code == 503
    assert first.json()["error"] == "database_unavailable"


def test_health_recovers_by_itself_once_the_database_answers_again(committed_db, pg_engine):
    """22/10/2026 - Compruebo que, pasada la caida, la API abre una conexion nueva y vuelve a contestar 200 sin reiniciarse."""
    app = create_app()
    with TestClient(app, raise_server_exceptions=False) as client:
        client.get("/api/health")
        _kill_pooled_connection(app, pg_engine)
        client.get("/api/health")  # esta peticion se come la conexion rota

        recovered = client.get("/api/health")  # el pool abre una conexion nueva

    assert recovered.status_code == 200
    assert recovered.json() == {"status": "ok"}
