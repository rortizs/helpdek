"""22/10/2026 - Rutas de avisos: los de quien hace la peticion, nunca los de otra persona (semana 15: via HelpDeskFacade)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies import CurrentUser, FacadeDep
from app.schemas.notifications import NotificationOut, ReadAllOut

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def unread_notifications(facade: FacadeDep, user: CurrentUser):
    """22/10/2026 - GET /api/notifications: avisos sin leer del usuario autenticado."""
    return facade.my_notifications(user)


@router.post("/read-all", response_model=ReadAllOut)
def read_all(facade: FacadeDep, user: CurrentUser):
    """22/10/2026 - POST /api/notifications/read-all: marca todo como leido y dice cuantos."""
    return ReadAllOut(updated=facade.mark_notifications_read(user))
