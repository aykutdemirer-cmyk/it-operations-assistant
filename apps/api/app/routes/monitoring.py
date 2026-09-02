import logging

from fastapi import APIRouter, HTTPException

from app.db.assets import get_connection, list_assets
from app.snmp.poller import PollBatchResult, PollingEngine

router = APIRouter(prefix="/api")

logger = logging.getLogger(__name__)


@router.get("/monitoring", response_model=PollBatchResult)
async def get_monitoring_overview() -> PollBatchResult:
    """Tüm asset'ler için gerçek bir SNMP polling turu çalıştırır ve
    toplu sonucu döner (Faz 24).

    - `assets` tablosundaki her asset için `profile_store.
      resolve_profile_for_asset` çağrılır — bu asset'e `asset_snmp_
      profiles` üzerinden atanmış aktif bir profil yoksa (ve `.env`
      fallback'i de çözülmezse) dürüstçe `status="not_configured"`
      döner.
    - Profili olan asset'ler `PollingEngine` ile gerçek SNMP poll'una
      tabi tutulur (`SNMP_MAX_CONCURRENCY` ile sınırlı eşzamanlılık).
    - Hiçbir sistem/interface/bant genişliği verisi uydurulmaz; veri
      yoksa `SNMPPollResult.system=None`/`interfaces=[]` kalır.
    - Bu endpoint `POST /api/snmp/poll/{asset_id}`'in YERİNE geçmez —
      o, tek bir asset'i anında poll etmek için var (ör. AssetDetails
      Monitoring sekmesi); bu endpoint ise TÜM filoyu tek turda görmek
      içindir (`/monitoring` sayfası için)."""
    try:
        conn = await get_connection()
    except OSError as exc:
        logger.warning("PostgreSQL erişilemedi, GET /api/monitoring başarısız")
        raise HTTPException(
            status_code=503, detail={"database": "unreachable"}
        ) from exc

    try:
        assets = await list_assets(conn)
        return await PollingEngine().poll_all(assets, conn)
    except Exception as exc:
        logger.exception("Asset listesi okunamadı (monitoring)")
        raise HTTPException(status_code=500, detail="Asset listesi alınamadı") from exc
    finally:
        await conn.close()
