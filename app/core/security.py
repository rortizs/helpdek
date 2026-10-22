"""22/10/2026 - Contrasenas con hash y tokens JWT (semana 14).

Aqui concentro todo lo criptografico para que las rutas nunca toquen secretos
directamente: si algo se filtra o se cambia de algoritmo, se toca un solo archivo.

Decisiones:
- Contrasenas con `hashlib.scrypt` de la biblioteca estandar: es lenta y gasta
  memoria a proposito (frena ataques por fuerza bruta) y no agrega dependencias.
  Cada hash lleva su propia sal y los parametros, asi se puede subir el costo
  mas adelante sin invalidar los hashes viejos.
- Tokens con PyJWT: mantenida, pequena, valida `exp` por nosotros. (python-jose y
  passlib, que usaba la version anterior, estan practicamente abandonadas.)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from functools import cache

import jwt

from app.core.config import get_secret_key, get_settings
from app.domain.errors import AuthenticationError

ALGORITHM = "HS256"
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2**14, 8, 1
SALT_BYTES = 16


# --- contrasenas ---------------------------------------------------------------

def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    # surrogatepass: un str con un surrogate suelto ("\ud800") no se puede codificar en
    # UTF-8 estricto y tumbaria el login con un 500; asi cualquier str se procesa igual.
    return hashlib.scrypt(password.encode("utf-8", errors="surrogatepass"), salt=salt, n=n, r=r, p=p, maxmem=64 * 1024 * 1024)


def hash_password(password: str) -> str:
    """22/10/2026 - Devuelve `scrypt$n$r$p$sal$hash`; la contrasena original no se guarda."""
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored_hash: str) -> bool:
    """22/10/2026 - True solo si coincide. Cualquier hash raro (como el "x" del seed) da False.

    Un hash ilegible tambien gasta el trabajo de scrypt antes de fallar: si
    respondiera al instante, quien mida el tiempo del login distinguiria a los
    usuarios del seed de los demas (y de los correos inexistentes).
    """
    try:
        scheme, n, r, p, salt, expected = stored_hash.split("$")
        if scheme != "scrypt":
            raise ValueError("unknown scheme")
        digest = _scrypt(password, base64.b64decode(salt), int(n), int(r), int(p))
        # compare_digest: tarda lo mismo acierte donde acierte (evita ataques de tiempo).
        return hmac.compare_digest(digest, base64.b64decode(expected))
    except (ValueError, TypeError):
        # Mismo costo que una verificacion real (parametros y sal fijos del proyecto).
        _scrypt(password, bytes(SALT_BYTES), SCRYPT_N, SCRYPT_R, SCRYPT_P)
        return False


@cache
def _dummy_hash() -> str:
    return hash_password(secrets.token_hex(16))


def waste_time_like_a_real_check(password: str) -> None:
    """22/10/2026 - Se llama cuando el correo no existe: tarda lo mismo que verificar una clave real,
    asi la demora de la respuesta no revela que correos estan registrados.
    (Un hash ilegible ya lo cubre `verify_password`; ver arriba.)"""
    verify_password(password, _dummy_hash())


# --- tokens ---------------------------------------------------------------------

def create_access_token(user_id: int, expires_delta: timedelta | None = None) -> str:
    """22/10/2026 - Token firmado con solo el id del usuario y su vencimiento.

    No lleva rol ni correo: se leen de la base en cada peticion, asi un cambio
    de rol (o borrar al usuario) surte efecto de inmediato.
    """
    # JWT exige UTC con zona; es la unica excepcion al reloj naive de app.domain.clock
    # porque estas fechas nunca llegan a la base de datos.
    issued = datetime.now(timezone.utc)
    ttl = expires_delta if expires_delta is not None else timedelta(minutes=get_settings().access_token_minutes)
    claims = {"sub": str(user_id), "iat": issued, "exp": issued + ttl}
    return jwt.encode(claims, get_secret_key(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> int:
    """22/10/2026 - Devuelve el id del usuario o lanza AuthenticationError (vencido, alterado, basura)."""
    try:
        claims = jwt.decode(
            token,
            get_secret_key(),
            algorithms=[ALGORITHM],  # fijo: nunca se acepta el algoritmo que diga el token
            options={"require": ["exp", "sub"]},
        )
        return int(claims["sub"])
    except (jwt.PyJWTError, ValueError, TypeError):
        raise AuthenticationError("invalid or expired token") from None
