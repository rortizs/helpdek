"""22/10/2026 - Eventos de dominio de un ticket (semana 15, patron Observer).

Antes, TicketService llamaba directamente al notificador cada vez que pasaba algo.
Cuando aparecio una segunda necesidad (dejar un registro de auditoria), la unica
salida era meter otra llamada en cada metodo del servicio. Ahora el servicio solo
cuenta QUE paso (un evento inmutable) y quien quiera reaccionar se suscribe.
Los eventos no saben nada de HTTP, de SQL ni de quien los escucha.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar

from app.domain.clock import now
from app.models.enums import TicketStatus


# 22/10/2026 - Base de todos los eventos: que ticket, quien lo provoco y cuando.
# `requester_id` viaja en el evento para que un suscriptor decida a quien avisar
# sin tener que volver a consultar el ticket.
@dataclass(frozen=True)
class TicketEvent:
    name: ClassVar[str] = "ticket_event"

    ticket_id: int
    actor_id: int
    requester_id: int
    occurred_at: datetime = field(default_factory=now, kw_only=True)


@dataclass(frozen=True)
class TicketCreated(TicketEvent):
    """22/10/2026 - Se abrio un ticket nuevo."""

    name: ClassVar[str] = "ticket_created"


@dataclass(frozen=True)
class TicketAssigned(TicketEvent):
    """22/10/2026 - Se asigno el ticket a un tecnico."""

    name: ClassVar[str] = "ticket_assigned"
    technician_id: int


@dataclass(frozen=True)
class TicketStatusChanged(TicketEvent):
    """22/10/2026 - El ticket cambio de estado (ya validada la transicion)."""

    name: ClassVar[str] = "ticket_status_changed"
    new_status: TicketStatus


@dataclass(frozen=True)
class TicketCommented(TicketEvent):
    """22/10/2026 - Alguien agrego un comentario."""

    name: ClassVar[str] = "ticket_commented"
    comment_id: int | None


@dataclass(frozen=True)
class TicketCancelled(TicketEvent):
    """22/10/2026 - El solicitante cancelo su ticket. Lo incluyo porque el notificador
    de las semanas anteriores ya avisaba de esto y no quiero perder ese comportamiento."""

    name: ClassVar[str] = "ticket_cancelled"
