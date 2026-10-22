"""22/10/2026 - Login: cambia correo + contrasena por un token con vencimiento (semana 14).

Semana 15: los dos pasos (autenticar + emitir token) viven en HelpDeskFacade.login.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies import FacadeDep
from app.schemas.auth import LoginRequest, TokenOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
def login(body: LoginRequest, facade: FacadeDep):
    """22/10/2026 - POST /api/auth/login: valida credenciales y devuelve el token Bearer."""
    token, expires_in = facade.login(body.email, body.password)
    return TokenOut(access_token=token, expires_in=expires_in)
