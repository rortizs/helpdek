"""22/10/2026 - Rutas de usuarios. Mismo patron que tickets: la ruta solo traduce, el servicio decide."""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.dependencies import CurrentUser, ServicesDep
from app.models.enums import Role
from app.schemas.users import UserCreate, UserOut

router = APIRouter(prefix="/users", tags=["users"])


# /me va ANTES de /{user_id}: si no, FastAPI intentaria leer "me" como un id.
@router.get("/me", response_model=UserOut)
def read_me(user: CurrentUser):
    """22/10/2026 - GET /api/users/me: quien soy segun mi token."""
    return user


@router.get("", response_model=list[UserOut])
def list_users(services: ServicesDep, user: CurrentUser, role: Role | None = None):
    return services.users.list_for(user, role=role)


@router.get("/{user_id}", response_model=UserOut)
def read_user(user_id: int, services: ServicesDep, user: CurrentUser):
    return services.users.require_for(user, user_id)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, services: ServicesDep, user: CurrentUser):
    return services.users.register_by(
        user, email=body.email, name=body.name, role=body.role, password=body.password
    )
