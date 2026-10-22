"""22/10/2026 - Esquemas de autenticacion: lo que entra y sale en el login."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=1, max_length=120)
    # Tope de largo: scrypt cuesta tiempo y memoria, no queremos que nos manden 10 MB.
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos
