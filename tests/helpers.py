"""22/10/2026 - Ayudas compartidas por las pruebas de la API (semana 14)."""

from __future__ import annotations

from functools import cache

from app.core.security import create_access_token, hash_password

# Contrasena de TODOS los usuarios del seed en `helpdesk_test` (ver conftest.py).
TEST_PASSWORD = "clave-de-prueba-123"
SEED_USER_IDS = range(1, 7)


def auth_headers(user_id: int) -> dict[str, str]:
    """Encabezado `Authorization: Bearer ...` de un usuario, sin pasar por el login."""
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


@cache
def seeded_password_hashes() -> dict[int, str]:
    """Un hash (con su sal) por usuario; se calcula una vez por sesion de pytest.

    scrypt es lento a proposito, asi que no se recalcula en cada prueba.
    """
    return {user_id: hash_password(TEST_PASSWORD) for user_id in SEED_USER_IDS}
