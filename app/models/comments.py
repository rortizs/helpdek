from dataclasses import dataclass, field
from datetime import datetime

from app.domain.clock import now


# 22/10/2026 - El comentario tampoco trae id propio: lo asigna la base al guardarlo.
@dataclass
class Comment:
    # None hasta que el repositorio guarda el objeto: la base asigna la llave.
    id: int | None = field(default=None, kw_only=True)
    ticket_id: int
    author_id: int
    body: str
    created_at: datetime = field(default_factory=now)
