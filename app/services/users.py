from app.models.entities import User
from app.models.enums import Role


class UserService:
    def __init__(self) -> None:
        self._users: list[User] = []
        self._next_id = 1

    def create(
        self,
        name: str,
        email: str,
        role: Role | str = Role.REQUESTER,
    ) -> User:
        normalized_email = email.strip().lower()
        if any(user.email == normalized_email for user in self._users):
            raise ValueError("email already exists")

        user = User(
            id=self._next_id,
            name=name,
            email=normalized_email,
            role=Role(role),
        )
        self._users.append(user)
        self._next_id += 1
        return user

    def by_id(self, user_id: int) -> User | None:
        for user in self._users:
            if user.id == user_id:
                return user
        return None

    def technicians(self) -> list[User]:
        return [user for user in self._users if user.role is Role.TECHNICIAN]
