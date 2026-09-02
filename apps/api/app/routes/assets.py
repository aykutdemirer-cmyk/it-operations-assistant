import logging
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.assets import get_connection, list_assets
from app.discovery.schemas import DeviceType, PortResult

router = APIRouter(prefix="/api")

logger = logging.getLogger(__name__)


class AssetResponse(BaseModel):
    id: UUID
    ip_address: str
    hostname: str | None
    mac_address: str | None
    vendor: str | None
    device_type: DeviceType
    confidence: Literal["high", "medium", "low"]
    evidence: list[str]
    open_ports: list[PortResult]
    status: str
    latency_ms: float | None
    last_seen: datetime
    created_at: datetime
    updated_at: datetime


@router.get("/assets", response_model=list[AssetResponse])
async def get_assets() -> list[AssetResponse]:
    try:
        conn = await get_connection()
    except OSError as exc:
        logger.warning("PostgreSQL erişilemedi, GET /api/assets başarısız")
        raise HTTPException(
            status_code=503, detail={"database": "unreachable"}
        ) from exc

    try:
        rows = await list_assets(conn)
    except Exception as exc:
        # Ham PostgreSQL hatasi (sema/sorgu detaylari) kullaniciya asla
        # dogrudan sizmaz — yalnizca sunucu loglarina yazilir.
        logger.exception("Asset listesi okunamadi")
        raise HTTPException(
            status_code=500, detail="Asset listesi alınamadı"
        ) from exc
    finally:
        await conn.close()

    return [
        AssetResponse(
            id=row["id"],
            ip_address=str(row["ip_address"]),
            hostname=row["hostname"],
            mac_address=row["mac_address"],
            vendor=row["vendor"],
            device_type=row["device_type"],
            confidence=row["confidence"],
            evidence=row["evidence"],
            open_ports=row["open_ports"],
            status=row["status"],
            latency_ms=row["latency_ms"],
            last_seen=row["last_seen"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]
