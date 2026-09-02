import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.db.snmp_profiles import ensure_schema, get_connection
from app.snmp import profile_service as service
from app.snmp.profile_config import SNMPProfileResponse, SNMPProfileWriteRequest
from app.snmp.profile_service import (
    SNMPProfileHasAssignmentsError,
    SNMPProfileNameConflictError,
    SNMPProfileNotFoundError,
    SNMPTestConnectionResult,
)

router = APIRouter(prefix="/api/snmp/profiles")

logger = logging.getLogger(__name__)


async def _connect():
    try:
        conn = await get_connection()
    except OSError as exc:
        logger.warning("PostgreSQL erişilemedi (snmp profiles)")
        raise HTTPException(status_code=503, detail={"database": "unreachable"}) from exc
    await ensure_schema(conn)
    return conn


@router.get("", response_model=list[SNMPProfileResponse])
async def list_profiles() -> list[SNMPProfileResponse]:
    conn = await _connect()
    try:
        return await service.list_profiles(conn)
    finally:
        await conn.close()


@router.post("", response_model=SNMPProfileResponse, status_code=201)
async def create_profile(request: SNMPProfileWriteRequest) -> SNMPProfileResponse:
    conn = await _connect()
    try:
        return await service.create_profile(conn, request)
    except SNMPProfileNameConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        await conn.close()


@router.get("/{profile_id}", response_model=SNMPProfileResponse)
async def get_profile(profile_id: UUID) -> SNMPProfileResponse:
    conn = await _connect()
    try:
        profile = await service.get_profile(conn, profile_id)
    finally:
        await conn.close()
    if profile is None:
        raise HTTPException(status_code=404, detail="Profil bulunamadı")
    return profile


@router.put("/{profile_id}", response_model=SNMPProfileResponse)
async def replace_profile(profile_id: UUID, request: SNMPProfileWriteRequest) -> SNMPProfileResponse:
    conn = await _connect()
    try:
        return await service.replace_profile(conn, profile_id, request)
    except SNMPProfileNameConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except SNMPProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Profil bulunamadı") from exc
    finally:
        await conn.close()


@router.delete("/{profile_id}", status_code=204)
async def delete_profile(profile_id: UUID) -> None:
    conn = await _connect()
    try:
        deleted = await service.delete_profile(conn, profile_id)
    except SNMPProfileHasAssignmentsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        await conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="Profil bulunamadı")


@router.post("/{profile_id}/test", response_model=SNMPTestConnectionResult)
async def test_connection(profile_id: UUID) -> SNMPTestConnectionResult:
    """Yalnızca kullanıcının bu profili kaydederken açıkça verdiği
    `target_host`'a karşı GERÇEK bir SNMP poll dener — kullanıcı bu
    endpoint'i çağırdığında (Settings UI'daki "Bağlantıyı Test Et"
    butonu). Otomatik/örtük bir tarama DEĞİLDİR (bkz. CLAUDE.md)."""
    conn = await _connect()
    try:
        return await service.test_connection(conn, profile_id)
    except SNMPProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Profil bulunamadı") from exc
    finally:
        await conn.close()
