"""22/10/2026 - Esquemas de usuarios. `UserOut` no tiene password_hash: lo que no se declara aqui no sale."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import Role


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: Role


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=120)
    role: Role = Role.REQUESTER
    # Opcional; nunca se devuelve en UserOut. El servicio guarda solo su hash.
    password: str | None = Field(default=None, min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def email_must_look_like_an_email(cls, value: str) -> str:
        if " " in value or value.count("@") != 1 or value.startswith("@") or value.endswith("@"):
            raise ValueError("email must look like name@domain")
        return value
