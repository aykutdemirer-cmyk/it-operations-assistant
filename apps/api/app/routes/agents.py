import logging
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.agents import service
from app.agents.download import ArtifactNotAvailableError, resolve_windows_agent_artifact
from app.agents.rdp import NoConnectableAddressError, build_rdp_file
from app.agents.wol import InvalidMacAddressError, send_magic_packet
from app.agents.exceptions import (
    AgentAuthenticationError,
    AgentNotFoundError,
    EnrollmentCodeAlreadyUsedError,
    EnrollmentCodeExpiredError,
    EnrollmentCodeInvalidError,
)
from app.agents.matching import AssetMatchCandidate
from app.agents.models import (
    AgentDetail,
    AgentHeartbeatRequest,
    AgentInventoryRequest,
    AgentRegistrationRequest,
    AgentRegistrationResponse,
    AgentSummary,
    AgentTelemetryRequest,
    EnrollmentCodeResponse,
    EnrollmentCodeSummary,
    WindowsAgentDownloadInfo,
)
from app.db.agents import ensure_schema, get_connection

router = APIRouter(prefix="/api/agents")

logger = logging.getLogger(__name__)


async def _connect():
    try:
        conn = await get_connection()
    except OSError as exc:
        logger.warning("PostgreSQL erişilemedi (agents)")
        raise HTTPException(status_code=503, detail={"database": "unreachable"}) from exc
    await ensure_schema(conn)
    return conn


@router.post("/register", response_model=AgentRegistrationResponse, status_code=201)
async def register(request: AgentRegistrationRequest) -> AgentRegistrationResponse:
    """Yeni bir agent kaydeder, tek seferlik bir bearer token döner.
    Token yalnızca BU response'ta görünür — bir daha hiçbir yerde
    (log, DB, başka bir response) plaintext olarak bulunmaz. Faz 31:
    geçerli, süresi dolmamış, daha önce kullanılmamış bir
    `enrollment_code` gerektirir (bkz. `app/agents/enrollment.py`)."""
    conn = await _connect()
    try:
        return await service.register_agent(conn, request)
    except EnrollmentCodeInvalidError as exc:
        raise HTTPException(status_code=401, detail="Enrollment code geçersiz") from exc
    except EnrollmentCodeExpiredError as exc:
        raise HTTPException(status_code=401, detail="Enrollment code süresi dolmuş") from exc
    except EnrollmentCodeAlreadyUsedError as exc:
        raise HTTPException(status_code=401, detail="Enrollment code daha önce kullanılmış") from exc
    finally:
        await conn.close()


@router.post("/enrollment-codes", response_model=EnrollmentCodeResponse, status_code=201)
async def create_enrollment_code() -> EnrollmentCodeResponse:
    """Yeni, tek kullanımlık, 10 dakika geçerli bir enrollment kodu
    üretir (Settings > Agent Configuration'daki "Kod Üret" butonu).
    Kod bir credential DEĞİLDİR — yalnızca "bu kaydı bir insan
    başlattı" onayıdır, plaintext döndürülmesi güvenlik ilkesini ihlal
    etmez."""
    conn = await _connect()
    try:
        row = await service.create_enrollment_code(conn)
        return EnrollmentCodeResponse(code=row["code"], expires_at=row["expires_at"])
    finally:
        await conn.close()


@router.get("/enrollment-codes", response_model=list[EnrollmentCodeSummary])
async def list_enrollment_codes() -> list[EnrollmentCodeSummary]:
    """Süresi dolmamış VE henüz kullanılmamış kodları döner."""
    conn = await _connect()
    try:
        rows = await service.list_enrollment_codes(conn)
        return [EnrollmentCodeSummary(code=r["code"], created_at=r["created_at"], expires_at=r["expires_at"]) for r in rows]
    finally:
        await conn.close()


@router.get("/download/windows/info", response_model=WindowsAgentDownloadInfo)
async def get_windows_agent_download_info() -> WindowsAgentDownloadInfo:
    """Gerçek build metadata'sı (Faz 32) — hiçbir zaman DB'ye dokunmaz,
    yalnızca `apps/agent/dist/build-info.json`'ı okur. Henüz build
    edilmemişse `available=False` (dürüstçe), asla uydurma bir
    versiyon/boyut YOK."""
    try:
        artifact = resolve_windows_agent_artifact()
    except ArtifactNotAvailableError:
        return WindowsAgentDownloadInfo(available=False)
    return WindowsAgentDownloadInfo(
        available=True,
        version=artifact.version,
        filename=artifact.filename,
        size_bytes=artifact.size_bytes,
        built_at=artifact.built_at,
    )


@router.get("/download/windows")
async def download_windows_agent() -> FileResponse:
    """Önceden build edilmiş Windows Agent EXE'sini indirir (Faz 32).
    Bu endpoint HİÇBİR ZAMAN PyInstaller çalıştırmaz — build/deployment
    tamamen ayrı (bkz. `packaging/windows/build.ps1`). Dosya adı/yolu
    kullanıcıdan/istekten ASLA alınmaz — tek kaynak sunucu tarafındaki
    `build-info.json` (bkz. `app/agents/download.py`, path traversal
    yapısal olarak imkansız). Artifact yoksa dürüst bir `404` döner —
    hiçbir sahte/placeholder dosya üretilmez."""
    try:
        artifact = resolve_windows_agent_artifact()
    except ArtifactNotAvailableError as exc:
        raise HTTPException(
            status_code=404,
            detail="Windows Agent EXE henüz build edilmemiş. Önce packaging/windows/build.ps1 çalıştırılmalı.",
        ) from exc
    return FileResponse(
        path=artifact.path,
        media_type="application/octet-stream",
        filename=f"IT-Operations-Agent-{artifact.version}.exe",
    )


async def _authenticate(conn, authorization: str | None) -> dict:
    try:
        return await service.authenticate(conn, authorization)
    except AgentAuthenticationError as exc:
        raise HTTPException(status_code=401, detail="Kimlik doğrulama başarısız") from exc


@router.post("/heartbeat", response_model=AgentSummary)
async def heartbeat(
    request: AgentHeartbeatRequest, authorization: str | None = Header(default=None)
) -> AgentSummary:
    conn = await _connect()
    try:
        agent = await _authenticate(conn, authorization)
        try:
            return await service.record_heartbeat(
                conn, agent, request.uptime_seconds, request.agent_version
            )
        except AgentNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Agent bulunamadı") from exc
    finally:
        await conn.close()


def _require_matching_agent(agent: dict, agent_id: UUID) -> None:
    """Bearer token'ın ait olduğu agent, URL'deki `{agent_id}` ile
    eşleşmeli — token geçerli olsa bile BAŞKA bir agent'ın id'si adına
    veri yazılamaz (path'teki id asla tek başına güvenilir kimlik
    olarak kabul edilmez, yalnızca token'la doğrulanmış agent'la
    tutarlılık kontrolü için kullanılır)."""
    if agent["id"] != agent_id:
        raise HTTPException(status_code=403, detail="Token bu agent'a ait değil")


@router.post("/{agent_id}/telemetry")
async def telemetry(
    agent_id: UUID,
    request: AgentTelemetryRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    conn = await _connect()
    try:
        agent = await _authenticate(conn, authorization)
        _require_matching_agent(agent, agent_id)
        await service.record_telemetry(conn, agent, request)
        return {"status": "ok"}
    finally:
        await conn.close()


@router.post("/{agent_id}/inventory")
async def inventory(
    agent_id: UUID,
    request: AgentInventoryRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    conn = await _connect()
    try:
        agent = await _authenticate(conn, authorization)
        _require_matching_agent(agent, agent_id)
        await service.record_inventory(conn, agent, request)
        return {"status": "ok"}
    finally:
        await conn.close()


@router.get("", response_model=list[AgentSummary])
async def list_agents_route() -> list[AgentSummary]:
    conn = await _connect()
    try:
        return await service.list_agent_summaries(conn)
    finally:
        await conn.close()


@router.get("/{agent_id}", response_model=AgentDetail)
async def get_agent_route(agent_id: UUID) -> AgentDetail:
    conn = await _connect()
    try:
        detail = await service.get_agent_detail(conn, agent_id)
    finally:
        await conn.close()
    if detail is None:
        raise HTTPException(status_code=404, detail="Agent bulunamadı")
    return detail


@router.get("/{agent_id}/connect/rdp")
async def download_rdp_file(agent_id: UUID) -> Response:
    """Faz 34 — Hızlı Bağlantı. Agent'ın bilinen `local_ip`'siyle
    dinamik bir `.rdp` dosyası üretir; tarayıcı bunu indirir, işletim
    sistemi genelde `mstsc.exe`'yi otomatik açar. Backend BAĞLANTIYI
    KENDİSİ KURMAZ — yalnızca istemcinin kendi RDP istemcisine bir
    yapılandırma dosyası verir. `local_ip` bilinmiyorsa dürüst bir
    `404` döner, uydurma bir adres YAZILMAZ."""
    conn = await _connect()
    try:
        detail = await service.get_agent_detail(conn, agent_id)
    finally:
        await conn.close()
    if detail is None:
        raise HTTPException(status_code=404, detail="Agent bulunamadı")

    try:
        content = build_rdp_file(
            local_ip=detail.local_ip,
            username=detail.latest_telemetry.last_logged_in_user if detail.latest_telemetry else None,
        )
    except NoConnectableAddressError as exc:
        raise HTTPException(status_code=404, detail="Agent'ın bilinen bir yerel IP adresi yok") from exc

    return Response(
        content=content,
        media_type="application/x-rdp",
        headers={"Content-Disposition": f'attachment; filename="{detail.hostname}.rdp"'},
    )


@router.post("/{agent_id}/wake")
async def wake_agent(agent_id: UUID) -> dict:
    """Faz 37 — Wake-on-LAN. Agent'ın kendisiyle HİÇ konuşmaz — bu
    yüzden cihaz Çevrimdışı iken de çalışır (WoL'un bütün amacı bu).
    Yalnızca DB'de bilinen `mac_address` kullanılır; bilinmiyorsa
    dürüst bir `404` döner, uydurma bir paket ASLA gönderilmez."""
    conn = await _connect()
    try:
        detail = await service.get_agent_detail(conn, agent_id)
    finally:
        await conn.close()
    if detail is None:
        raise HTTPException(status_code=404, detail="Agent bulunamadı")
    if not detail.mac_address:
        raise HTTPException(status_code=404, detail="Agent'ın bilinen bir MAC adresi yok")

    try:
        send_magic_packet(detail.mac_address)
    except InvalidMacAddressError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=502, detail=f"Magic packet gönderilemedi: {exc}") from exc

    return {"status": "sent", "mac_address": detail.mac_address}


@router.get("/{agent_id}/asset-match", response_model=AssetMatchCandidate)
async def get_asset_match(agent_id: UUID) -> AssetMatchCandidate:
    """Bu agent için mevcut `assets` listesine karşı bir eşleştirme
    DEĞERLENDİRMESİ döner — hiçbir şey YAZMAZ (bkz. `app/agents/
    matching.py`). `confidence="candidate"` ise frontend/insan bunu
    `POST` ile AÇIKÇA onaylamalı; otomatik uygulanmaz."""
    conn = await _connect()
    try:
        return await service.evaluate_agent_asset_match(conn, agent_id)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Agent bulunamadı") from exc
    finally:
        await conn.close()


class ConfirmAssetMatchRequest(BaseModel):
    asset_id: UUID


@router.post("/{agent_id}/asset-match", response_model=AgentSummary)
async def confirm_asset_match(
    agent_id: UUID, request: ConfirmAssetMatchRequest
) -> AgentSummary:
    """Bir agent↔asset eşleşmesini AÇIKÇA onaylar — yalnızca bu endpoint
    `agents.asset_id`'yi yazabilir, hiçbir otomatik süreç yazmaz."""
    conn = await _connect()
    try:
        return await service.confirm_agent_asset_match(conn, agent_id, request.asset_id)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    finally:
        await conn.close()
