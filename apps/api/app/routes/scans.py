import logging
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.scans import get_connection, list_scans

router = APIRouter(prefix="/api")

logger = logging.getLogger(__name__)


class ScanResponse(BaseModel):
    id: UUID
    cidr: str
    started_at: datetime
    completed_at: datetime | None
    duration_ms: float | None
    hosts_scanned: int
    hosts_discovered: int
    open_ports: int
    status: Literal["running", "completed", "failed"]


@router.get("/scans", response_model=list[ScanResponse])
async def get_scans() -> list[ScanResponse]:
    try:
        conn = await get_connection()
    except OSError as exc:
        logger.warning("PostgreSQL erişilemedi, GET /api/scans başarısız")
        raise HTTPException(
            status_code=503, detail={"database": "unreachable"}
        ) from exc

    try:
        rows = await list_scans(conn)
    except Exception as exc:
        logger.exception("Scan geçmişi okunamadı")
        raise HTTPException(
            status_code=500, detail="Scan geçmişi alınamadı"
        ) from exc
    finally:
        await conn.close()

    return [ScanResponse(**row) for row in rows]
