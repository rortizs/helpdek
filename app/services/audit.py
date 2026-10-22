"""22/10/2026 - Suscriptor de auditoria (semana 15): una linea de log por evento.

Es el segundo suscriptor que tiene el sistema, y justo por eso el patron Observer
se justifica: agregarlo no obligo a tocar TicketService.
"""

from __future__ import annotations

import logging

from app.domain.events import TicketEvent

audit_logger = logging.getLogger("helpdesk.audit")


class AuditLogSubscriber:
    """22/10/2026 - Escribe `event=<nombre> ticket=<id> actor=<id>` con el modulo logging.

    No guarda ni el titulo ni el cuerpo de los comentarios: un log no es lugar para
    datos de las personas.
    """

    def __call__(self, event: TicketEvent) -> None:
        audit_logger.info(
            "event=%s ticket=%s actor=%s", event.name, event.ticket_id, event.actor_id
        )
