import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.db.assets import get_asset_by_id, get_connection
from app.snmp.client import SNMPClient
from app.snmp.exceptions import SNMPError
from app.snmp.models import SNMPPollResult
from app.snmp.profile_store import resolve_profile_for_asset

router = APIRouter(prefix="/api")

logger = logging.getLogger(__name__)


@router.post("/snmp/poll/{asset_id}", response_model=SNMPPollResult)
async def poll_asset_snmp(asset_id: UUID) -> SNMPPollResult:
    """Bir asset için SNMP poll dener.

    - Profil çözümü `app/snmp/profile_store.py::resolve_profile_for_asset`
      ile yapılır: önce bu asset'e `asset_snmp_profiles` üzerinden
      atanmış (ve `enabled=True`) bir `snmp_profiles` kaydı aranır;
      atama yoksa geriye dönük uyumluluk için `.env` tabanlı tek-hedef
      fallback denenir. Hiçbiri çözülemezse sonuç her zaman
      `status="not_configured"` döner; `system`/`interfaces` asla
      uydurulmuş bir değerle doldurulmaz.
    - Bir profil çözülürse `app/snmp/client.py` ile GERÇEK bir SNMPv2c
      poll denenir. Hiçbir SNMP/kütüphane seviyesi hata sahte bir HTTP
      200 "success" olarak gizlenmez — `SNMPPollResult.status` gerçek
      sonucu yansıtır (`unreachable`/`timeout`/`authentication_failed`/
      `partial`/`success`). Community/secret DEĞERİ bu response'un
      hiçbir alanına asla yazılmaz (bkz. `secrets.py`)."""
    try:
        conn = await get_connection()
    except OSError as exc:
        logger.warning("PostgreSQL erişilemedi, POST /api/snmp/poll başarısız")
        raise HTTPException(
            status_code=503, detail={"database": "unreachable"}
        ) from exc

    try:
        asset = await get_asset_by_id(conn, asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Asset bulunamadı")
        profile = await resolve_profile_for_asset(conn, asset)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Asset okunamadı (SNMP poll)")
        raise HTTPException(status_code=500, detail="Asset okunamadı") from exc
    finally:
        await conn.close()

    if profile is None:
        return SNMPPollResult(
            asset_id=asset_id,
            polled_at=datetime.now(timezone.utc),
            status="not_configured",
            error="SNMP credential/community bu asset için henüz yapılandırılmadı.",
        )

    try:
        # `str(...)`: `assets.ip_address` (INET) asyncpg'de bir
        # `ipaddress.IPv4Address` nesnesi olarak gelir — bkz. `app/snmp/
        # poller.py::_poll_one`'daki AYNI düzeltmenin gerekçesi.
        return await SNMPClient().poll_asset(profile, str(asset["ip_address"]), asset_id)
    except SNMPError:
        # `SNMPClient.poll_asset` normal şartlarda kendi hatalarını
        # yakalayıp `SNMPPollResult.status` üzerinden döner; buraya
        # yalnızca beklenmeyen bir durumda düşer. Yine de gerçek
        # library/istisna detayını HTTP katmanına sızdırmadan, dürüst
        # bir `unreachable` sonucu döneriz.
        logger.exception("SNMP poll beklenmeyen şekilde başarısız (asset_id=%s)", asset_id)
        return SNMPPollResult(
            asset_id=asset_id,
            polled_at=datetime.now(timezone.utc),
            status="unreachable",
            error="SNMP poll sırasında beklenmeyen bir hata oluştu.",
        )
