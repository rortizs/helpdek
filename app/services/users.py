# 22/10/2026 - Agrego esta linea para que el proyecto funcione en Python 3.11 a 3.13:
# la clase define un metodo llamado `list` y, sin ella, la anotacion `list[...]`
# se evaluaria contra ese metodo y no contra el tipo nativo (TypeError al importar).
from __future__ import annotations

from app.domain.errors import (
    ConflictError,
    PermissionDeniedError,
    UserNotFoundError,
    ValidationError,
)
from app.core.security import hash_password
from app.models.entities import User
from app.models.enums import Role
from app.repositories.base import UserRepository


class UserService:
    """22/10/2026 - Registro y consulta de usuarios; el id lo asigna el repositorio."""

    def __init__(self, repository: UserRepository) -> None:
        self._repository = repository

    def register(
        self,
        email: str,
        name: str,
        role: Role | str = Role.REQUESTER,
    ) -> User:
        if "@" not in email and "@" in name:
            email, name = name, email

        normalized_email = email.strip().lower()
        if not normalized_email:
            raise ValidationError("email is required", field="email")
        if self._repository.by_email(normalized_email) is not None:
            raise ConflictError(
                "email already exists",
                field="email",
                email=normalized_email,
            )

        user = User(
            name=name,
            email=normalized_email,
            role=Role(role),
        )
        return self._repository.add(user)

    def register_by(
        self,
        actor: User,
        email: str,
        name: str,
        role: Role | str = Role.REQUESTER,
        password: str | None = None,
    ) -> User:
        """22/10/2026 - Crear usuarios es cosa de administradores.

        Sin contrasena el usuario queda sin poder iniciar sesion hasta que se le
        asigne una (scripts/set_password.py).
        """
        if Role(actor.role) is not Role.ADMINISTRATOR:
            raise PermissionDeniedError("Only administrators can create users", actor_id=actor.id)
        user = self.register(email=email, name=name, role=role)
        if password is not None:
            self._repository.set_password_hash(user.id, hash_password(password))
        return user

    def list_for(self, actor: User, role: Role | str | None = None) -> list[User]:
        """22/10/2026 - Ver la lista de usuarios es solo del personal."""
        if not actor.is_staff:
            raise PermissionDeniedError("Only staff users can list users", actor_id=actor.id)
        users = self._repository.all()
        if role is not None:
            users = [user for user in users if Role(user.role) is Role(role)]
        return users

    def require_for(self, actor: User, user_id: int) -> User:
        """22/10/2026 - El personal ve a cualquiera; los demas, solo a si mismos."""
        if not actor.is_staff and actor.id != user_id:
            raise PermissionDeniedError(
                "You can only read your own user", actor_id=actor.id, user_id=user_id
            )
        return self.require(user_id)

    def create(
        self,
        name: str,
        email: str,
        role: Role | str = Role.REQUESTER,
    ) -> User:
        return self.register(email=email, name=name, role=role)

    def require(self, user_id: int) -> User:
        user = self._repository.by_id(user_id)
        if user is None:
            raise UserNotFoundError(user_id)
        return user

    def by_id(self, user_id: int) -> User | None:
        return self._repository.by_id(user_id)

    def by_email(self, email: str) -> User | None:
        return self._repository.by_email(email)

    def technicians(self) -> list[User]:
        assignable_roles = {Role.TECHNICIAN, Role.SUPERVISOR}
        return [
            user
            for user in self._repository.all()
            if Role(user.role) in assignable_roles
        ]
