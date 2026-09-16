import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.db.asset_snmp_profiles import get_connection
from app.snmp import asset_profile_service as service
from app.snmp.asset_profile_service import AssetNotFoundError, AssetSnmpProfileResponse, AssetSummary
from app.snmp.profile_service import SNMPProfileNotFoundError

router = APIRouter(prefix="/api")

logger = logging.getLogger(__name__)


async def _connect():
    try:
        conn = await get_connection()
    except OSError as exc:
        logger.warning("PostgreSQL erişilemedi (asset-snmp-profile)")
        raise HTTPException(status_code=503, detail={"database": "unreachable"}) from exc
    # Şema artık uygulama başlangıcında tek seferlik kurulur (bkz.
    # `app/main.py::_ensure_schema_once`).
    return conn


@router.get("/assets/{asset_id}/snmp-profile", response_model=AssetSnmpProfileResponse)
async def get_asset_snmp_profile(asset_id: UUID) -> AssetSnmpProfileResponse:
    conn = await _connect()
    try:
        return await service.get_profile_for_asset(conn, asset_id)
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Asset bulunamadı") from exc
    finally:
        await conn.close()


@router.put("/assets/{asset_id}/snmp-profile/{profile_id}")
async def assign_snmp_profile(asset_id: UUID, profile_id: UUID) -> dict:
    """Asset'e bir SNMP profili atar (zaten atanmış bir profil varsa
    ÜZERİNE YAZAR — bu, "farklı bir profil seç" akışının kendisidir)."""
    conn = await _connect()
    try:
        await service.assign_profile_to_asset(conn, asset_id, profile_id)
        return {"status": "assigned"}
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Asset bulunamadı") from exc
    except SNMPProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Profil bulunamadı") from exc
    finally:
        await conn.close()


@router.delete("/assets/{asset_id}/snmp-profile")
async def unassign_snmp_profile(asset_id: UUID) -> dict:
    conn = await _connect()
    try:
        await service.unassign_profile_from_asset(conn, asset_id)
        return {"status": "unassigned"}
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Asset bulunamadı") from exc
    finally:
        await conn.close()


@router.get("/snmp/profiles/{profile_id}/assets", response_model=list[AssetSummary])
async def list_profile_assets(profile_id: UUID) -> list[AssetSummary]:
    conn = await _connect()
    try:
        return await service.list_assets_for_profile(conn, profile_id)
    except SNMPProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Profil bulunamadı") from exc
    finally:
        await conn.close()
