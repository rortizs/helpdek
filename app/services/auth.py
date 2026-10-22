"""22/10/2026 - Autenticacion: comprueba correo + contrasena y emite el token (semana 14)."""

from __future__ import annotations

from datetime import timedelta

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    verify_password,
    waste_time_like_a_real_check,
)
from app.domain.errors import AuthenticationError
from app.models.entities import User
from app.repositories.base import UserRepository


class AuthService:
    """22/10/2026 - Caso de uso de login. Dice lo mismo falle donde falle para no filtrar correos."""

    def __init__(self, repository: UserRepository) -> None:
        self._repository = repository

    def authenticate(self, email: str, password: str) -> User:
        """22/10/2026 - Devuelve el usuario o lanza el MISMO error se falle donde se falle.

        Un mensaje distinto para "correo inexistente" y "clave incorrecta" le
        permitiria a un atacante averiguar que correos estan registrados.
        """
        stored_hash = self._repository.password_hash_for(email)
        if stored_hash is None:
            waste_time_like_a_real_check(password)
        elif verify_password(password, stored_hash):
            user = self._repository.by_email(email)
            if user is not None:
                return user
        raise AuthenticationError("invalid email or password")

    def issue_token(self, user: User) -> tuple[str, int]:
        """22/10/2026 - (token, segundos de vida)."""
        minutes = get_settings().access_token_minutes
        return create_access_token(user.id, expires_delta=timedelta(minutes=minutes)), minutes * 60
