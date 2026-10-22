"""22/10/2026 - Login: cambia correo + contrasena por un token con vencimiento (semana 14)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies import ServicesDep
from app.schemas.auth import LoginRequest, TokenOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(body: LoginRequest, services: ServicesDep):
    """22/10/2026 - POST /api/auth/login: valida credenciales y devuelve el token Bearer."""
    user = services.auth.authenticate(body.email, body.password)
    token, expires_in = services.auth.issue_token(user)
    return TokenOut(access_token=token, expires_in=expires_in)
