"""22/10/2026 - Rutas de tickets. Cada ruta hace tres cosas: recibir, llamar al servicio, responder.

Las reglas de negocio (incluidos los permisos) viven en TicketService; los
errores de dominio los traduce app/api/errors.py. Desde la semana 15 la ruta
tampoco elige el servicio: le pide el caso de uso a HelpDeskFacade.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.dependencies import CurrentUser, FacadeDep
from app.models.enums import TicketStatus
from app.schemas.tickets import (
    AssignRequest,
    CommentCreate,
    CommentOut,
    PriorityChange,
    StatusChange,
    TicketCreate,
    TicketDetailOut,
    TicketOut,
)

router = APIRouter(prefix="/tickets", tags=["tickets"])


# 22/10/2026 - GET /api/tickets: filtros + paginacion (limit/offset). El total viaja en
# el encabezado X-Total-Count para que el cuerpo siga siendo una lista simple.
@router.get("", response_model=list[TicketOut])
def list_tickets(
    response: Response,
    facade: FacadeDep,
    user: CurrentUser,
    status: TicketStatus | None = None,
    category: str | None = None,
    priority: str | None = None,
    requester_id: int | None = None,
    assignee_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    page = facade.list_tickets(
        user,
        status=status,
        category=category,
        priority=priority,
        requester_id=requester_id,
        assignee_id=assignee_id,
        limit=limit,
        offset=offset,
    )
    # La respuesta sigue siendo una lista; el total viaja en un encabezado.
    response.headers["X-Total-Count"] = str(page.total)
    return page.items


@router.get("/{ticket_id}", response_model=TicketDetailOut)
def get_ticket(ticket_id: int, facade: FacadeDep, user: CurrentUser):
    return facade.get_ticket(user, ticket_id)


@router.post("", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
def create_ticket(body: TicketCreate, facade: FacadeDep, user: CurrentUser):
    """22/10/2026 - POST /api/tickets: el solicitante es el usuario autenticado, no lo manda el cliente."""
    # El solicitante es quien hace la peticion; el estado inicial lo fija el
    # servicio. Lo que el cliente envie de mas se ignora.
    return facade.open_ticket(
        user,
        title=body.title,
        description=body.description,
        category=body.category,
        priority=body.priority,
    )


# --- comentarios ------------------------------------------------------------

@router.get("/{ticket_id}/comments", response_model=list[CommentOut])
def list_comments(ticket_id: int, facade: FacadeDep, user: CurrentUser):
    return facade.list_comments(user, ticket_id)


@router.post(
    "/{ticket_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
)
def add_comment(ticket_id: int, body: CommentCreate, facade: FacadeDep, user: CurrentUser):
    return facade.comment(user, ticket_id, body.body)


# --- acciones: cada una devuelve el ticket ya actualizado ---------------------

@router.post("/{ticket_id}/assign", response_model=TicketOut)
# 22/10/2026 - Las acciones (assign, status, priority, cancel) no tienen logica: solo
# llaman al servicio, que es quien valida permisos y transiciones.
def assign_ticket(ticket_id: int, body: AssignRequest, facade: FacadeDep, user: CurrentUser):
    return facade.assign(user, ticket_id, body.technician_id)


@router.patch("/{ticket_id}/status", response_model=TicketOut)
def change_status(ticket_id: int, body: StatusChange, facade: FacadeDep, user: CurrentUser):
    return facade.change_status(user, ticket_id, body.status)


@router.patch("/{ticket_id}/priority", response_model=TicketOut)
def change_priority(ticket_id: int, body: PriorityChange, facade: FacadeDep, user: CurrentUser):
    return facade.change_priority(user, ticket_id, body.priority)


@router.post("/{ticket_id}/cancel", response_model=TicketOut)
def cancel_ticket(ticket_id: int, facade: FacadeDep, user: CurrentUser):
    return facade.cancel(user, ticket_id)
