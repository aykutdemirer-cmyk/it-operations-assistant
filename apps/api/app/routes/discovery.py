import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.db.assets import ensure_schema, get_connection, upsert_asset
from app.db import scans as scans_repo
from app.discovery.cidr import InvalidCIDRError
from app.discovery.schemas import ICMPScanRequest, ScanResult
from app.discovery.scanner import scan_network

router = APIRouter(prefix="/api/discovery")

logger = logging.getLogger(__name__)


@router.post("/icmp", response_model=ScanResult)
async def post_icmp_scan(request: ICMPScanRequest) -> ScanResult:
    started_at = datetime.now(timezone.utc)
    scan_id = await start_scan_record(request.cidr, started_at)

    try:
        result = await scan_network(request.cidr)
    except InvalidCIDRError as exc:
        await fail_scan_record(scan_id, started_at)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        await fail_scan_record(scan_id, started_at)
        raise

    await persist_scan_result(result)
    await complete_scan_record(scan_id, started_at, result)
    return result


async def persist_scan_result(scan_result: ScanResult) -> None:
    """Discovery sonucundaki UP host'ları Asset Repository (`upsert_asset`)
    üzerinden `assets` tablosuna yazar.

    Yalnızca `status == "up"` olan host'lar yazılır — "bulunan" bir cihaz
    yanıt veren cihazdır; taranıp yanıt vermeyen (down) her IP için
    tabloda anlamsız bir satır oluşturmak asset envanterini bir /24'teki
    boş adreslerle doldurur. Bilinen bir cihaz artık yanıt vermiyorsa bu
    fonksiyon onu `down` olarak GÜNCELLEMEZ (kaydını olduğu gibi
    bırakır) — var olan asset'leri "artık görünmüyor" diye işaretlemek
    ayrı bir reconciliation kararı gerektirir, bu adımın kapsamı dışında.

    Discovery ile database katmanı arasındaki tek temas noktası burasıdır
    (route katmanı); `app/discovery/*` hiçbir zaman `app/db/*`'yi
    içe aktarmaz.

    PostgreSQL'e hiç bağlanılamazsa (`OSError`) veya tek bir host'un
    upsert'i başarısız olursa: discovery yanıtını ETKİLEMEZ, hata
    fırlatılmaz — yalnızca loglanır. Bir host'un DB hatası diğer
    host'ların yazılmasını engellemez (host bazında izole edilir)."""
    try:
        conn = await get_connection()
    except OSError:
        logger.warning(
            "PostgreSQL erişilemedi, discovery sonucu (cidr=%s) veritabanına "
            "yazılamadı",
            scan_result.cidr,
        )
        return

    up_hosts = [host for host in scan_result.hosts if host.status == "up"]
    saved = 0
    seen_at = datetime.now(timezone.utc)
    try:
        await ensure_schema(conn)
        for host in up_hosts:
            try:
                await upsert_asset(
                    conn,
                    ip_address=host.ip,
                    hostname=host.hostname,
                    mac_address=host.mac_address,
                    vendor=host.vendor,
                    device_type=host.device_type,
                    confidence=host.confidence,
                    status=host.status,
                    open_ports=[port.model_dump() for port in host.open_ports],
                    evidence=host.evidence,
                    last_seen=seen_at,
                    latency_ms=host.latency_ms,
                )
                saved += 1
            except Exception:
                logger.exception(
                    "Asset kaydı başarısız, host atlanıyor: ip=%s", host.ip
                )
    finally:
        await conn.close()

    logger.info(
        "Discovery sonucu kaydedildi: cidr=%s, kaydedilen=%d/%d (up host)",
        scan_result.cidr,
        saved,
        len(up_hosts),
    )


async def start_scan_record(cidr: str, started_at: datetime) -> UUID | None:
    """Tarama başlamadan önce `scans` tablosuna `running` durumunda bir
    kayıt açar (best-effort). PostgreSQL erişilemezse veya yazım
    başarısız olursa `None` döner ve discovery akışı hiç etkilenmeden
    devam eder — scan history, discovery'nin ana işlevini bloke eden bir
    bağımlılık değildir."""
    try:
        conn = await scans_repo.get_connection()
    except OSError:
        logger.warning("PostgreSQL erişilemedi, scan geçmişi kaydı başlatılamadı")
        return None

    try:
        await scans_repo.ensure_schema(conn)
        row = await scans_repo.create_scan(conn, cidr=cidr, started_at=started_at)
        return row["id"]
    except Exception:
        logger.exception("Scan geçmişi kaydı oluşturulamadı: cidr=%s", cidr)
        return None
    finally:
        await conn.close()


async def complete_scan_record(
    scan_id: UUID | None, started_at: datetime, result: ScanResult
) -> None:
    """Scan kaydını istatistikleriyle `completed` olarak günceller
    (best-effort — `start_scan_record` başarısız olduysa `scan_id` zaten
    `None`'dır, bu durumda hiçbir şey yapılmaz)."""
    if scan_id is None:
        return

    try:
        conn = await scans_repo.get_connection()
    except OSError:
        logger.warning("PostgreSQL erişilemedi, scan geçmişi güncellenemedi")
        return

    try:
        completed_at = datetime.now(timezone.utc)
        duration_ms = (completed_at - started_at).total_seconds() * 1000
        open_ports_count = sum(len(host.open_ports) for host in result.hosts)
        await scans_repo.complete_scan(
            conn,
            scan_id=scan_id,
            completed_at=completed_at,
            duration_ms=duration_ms,
            hosts_scanned=result.total_hosts,
            hosts_discovered=result.alive_hosts,
            open_ports=open_ports_count,
        )
    except Exception:
        logger.exception("Scan geçmişi tamamlanamadı: scan_id=%s", scan_id)
    finally:
        await conn.close()


async def fail_scan_record(scan_id: UUID | None, started_at: datetime) -> None:
    """Scan kaydını `failed` olarak günceller (best-effort)."""
    if scan_id is None:
        return

    try:
        conn = await scans_repo.get_connection()
    except OSError:
        logger.warning("PostgreSQL erişilemedi, scan geçmişi failed olarak işaretlenemedi")
        return

    try:
        completed_at = datetime.now(timezone.utc)
        duration_ms = (completed_at - started_at).total_seconds() * 1000
        await scans_repo.fail_scan(
            conn, scan_id=scan_id, completed_at=completed_at, duration_ms=duration_ms
        )
    except Exception:
        logger.exception("Scan geçmişi failed olarak işaretlenemedi: scan_id=%s", scan_id)
    finally:
        await conn.close()
