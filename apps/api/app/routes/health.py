import logging

from fastapi import APIRouter, HTTPException

from app.db.connection import check_db_connection
from app.db.snmp_profiles import get_connection
from app.snmp.profile_service import list_profiles

router = APIRouter(prefix="/api")

logger = logging.getLogger(__name__)


@router.get("/health")
def get_health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/db")
async def get_health_db() -> dict[str, str]:
    try:
        await check_db_connection()
    except OSError as exc:
        raise HTTPException(
            status_code=503, detail={"database": "unreachable"}
        ) from exc
    return {"database": "ok"}


@router.get("/health/snmp")
async def get_health_snmp() -> dict[str, str]:
    """En az bir `snmp_profiles` kaydı gerçekten `ready` (etkin VE
    credential'ı çözülmüş) durumdaysa `configured` döner — Faz: daha
    önce bu endpoint her zaman sabit `not_configured` dönüyordu, Ayarlar
    sayfasındaki "SNMP Durumu" da bunu (gerçek profil varlığına
    bakmaksızın) sabit gösteriyordu. PostgreSQL'e erişilemezse (ya da
    hiç profil yoksa) dürüstçe `not_configured` — asla "configured"
    UYDURULMAZ."""
    try:
        conn = await get_connection()
    except OSError:
        logger.warning("PostgreSQL erişilemedi, GET /api/health/snmp not_configured dönüyor")
        return {"snmp": "not_configured"}

    try:
        profiles = await list_profiles(conn)
    finally:
        await conn.close()

    if any(profile.status == "ready" for profile in profiles):
        return {"snmp": "configured"}
    return {"snmp": "not_configured"}
