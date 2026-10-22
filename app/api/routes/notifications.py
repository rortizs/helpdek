"""22/10/2026 - Rutas de avisos: los de quien hace la peticion, nunca los de otra persona."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.dependencies import CurrentUser, ServicesDep
from app.schemas.notifications import NotificationOut, ReadAllOut

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def unread_notifications(services: ServicesDep, user: CurrentUser):
    """22/10/2026 - GET /api/notifications: avisos sin leer del usuario autenticado."""
    return services.notifications.unread_for(user.id)


@router.post("/read-all", response_model=ReadAllOut)
def read_all(services: ServicesDep, user: CurrentUser):
    """22/10/2026 - POST /api/notifications/read-all: marca todo como leido y dice cuantos."""
    return ReadAllOut(updated=services.notifications.mark_all_read(user.id))
