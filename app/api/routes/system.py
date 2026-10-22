"""22/10/2026 - Rutas de sistema: comprobar que la aplicacion y la base responden."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import DbSession

router = APIRouter(tags=["system"])


@router.get("/health")
def health(db: DbSession):
    """22/10/2026 - GET /api/health: 200 si la base contesta, 503 con mensaje fijo si no."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        # Mensaje fijo: el error original puede incluir usuario y host de la base.
        return JSONResponse(
            status_code=503,
            content={
                "error": "database_unavailable",
                "message": "the database is not reachable",
                "details": {},
            },
        )
    return {"status": "ok"}
