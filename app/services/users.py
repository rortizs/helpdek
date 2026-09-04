from app.domain.errors import UserNotFoundError, ValidationError
from app.models.entities import User
from app.models.enums import Role
from app.repositories.base import UserRepository


class UserService:
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
            raise ValidationError(
                "email already exists",
                field="email",
                email=normalized_email,
            )

        user = User(
            id=self._repository.next_id(),
            name=name,
            email=normalized_email,
            role=Role(role),
        )
        return self._repository.add(user)

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
