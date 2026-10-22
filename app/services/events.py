"""22/10/2026 - EventPublisher: la lista de suscriptores del patron Observer (semana 15).

Lo hice a proposito minimo: una lista y un `for`. Un suscriptor es cualquier
funcion (o clase con `__call__`) que reciba el evento; `lista.append` ya sirve
como suscriptor en las pruebas. Sin colas, sin hilos, sin bus de mensajes.

Regla importante: los suscriptores corren de forma SINCRONA y en la MISMA
transaccion de la operacion. Si uno lanza una excepcion, la operacion falla y la
unidad de trabajo (session_scope) hace rollback: nunca queda un ticket guardado
sin su aviso. El costo es que un suscriptor lento o roto frena la peticion; si
algun dia hace falta aislarlos, ese es el momento de pensar en una cola.
"""

from __future__ import annotations

from collections.abc import Callable

from app.domain.events import TicketEvent

TicketEventSubscriber = Callable[[TicketEvent], None]


class EventPublisher:
    """22/10/2026 - Guarda los suscriptores y les entrega cada evento, en orden de alta."""

    def __init__(self) -> None:
        self._subscribers: list[TicketEventSubscriber] = []

    def subscribe(self, subscriber: TicketEventSubscriber) -> None:
        self._subscribers.append(subscriber)

    def unsubscribe(self, subscriber: TicketEventSubscriber) -> None:
        self._subscribers.remove(subscriber)

    def publish(self, event: TicketEvent) -> None:
        # Copia de la lista: un suscriptor puede darse de baja mientras se publica.
        for subscriber in list(self._subscribers):
            subscriber(event)
