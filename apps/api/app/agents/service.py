"""Agent alt sisteminin servis (orkestrasyon) katmanı — route'lar ile
`app/db/agents.py` arasında (bkz. `app/snmp/client.py`'nin SNMP için
oynadığı rol). Auth doğrulama, token üretimi/hash'leme ve `AgentStatus`
türetme mantığı burada yaşar; route'lar yalnızca HTTP/DB-erişilemez
hatalarını ele alır."""

import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

import asyncpg

from app.agents import enrollment
from app.agents.authentication import extract_bearer_token, generate_token, hash_token
from app.agents.exceptions import AgentAuthenticationError, AgentNotFoundError
from app.agents.matching import AssetMatchCandidate, evaluate_asset_match
from app.agents.models import (
    AgentDetail,
    AgentDeleteResult,
    AgentInventoryRequest,
    AgentRegistrationRequest,
    AgentRegistrationResponse,
    AgentRetentionPolicy,
    AgentStatus,
    AgentSummary,
    AgentTelemetryRequest,
    ArchivedAgentSummary,
)
from app.db import agent_enrollment as enrollment_repo
from app.db import agents as agents_repo
from app.db import assets as assets_repo

_DEFAULT_OFFLINE_THRESHOLD_SECONDS = 120

# Faz 29 karar: `agent_telemetry` yüksek frekanslı büyüyen bir tablo —
# gerçek bir Agent filosu üretime alınmadan önce bir retention politikası
# ZORUNLU (bkz. docs/decisions.md). 30 gün, çoğu NOC/monitoring aracının
# "kısa vadeli ham veri" varsayılanıyla tutarlı bir başlangıç değeri —
# credential DEĞİL, sıradan bir sayısal ayar, bu yüzden diğer env
# değerleri gibi (`AGENT_OFFLINE_THRESHOLD_SECONDS` vb.) ele alınır.
_DEFAULT_TELEMETRY_RETENTION_DAYS = 30


def _offline_threshold_seconds() -> int:
    raw = os.environ.get("AGENT_OFFLINE_THRESHOLD_SECONDS")
    if not raw:
        return _DEFAULT_OFFLINE_THRESHOLD_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_OFFLINE_THRESHOLD_SECONDS
    return value if value > 0 else _DEFAULT_OFFLINE_THRESHOLD_SECONDS


def telemetry_retention_days() -> int:
    raw = os.environ.get("AGENT_TELEMETRY_RETENTION_DAYS")
    if not raw:
        return _DEFAULT_TELEMETRY_RETENTION_DAYS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_TELEMETRY_RETENTION_DAYS
    return value if value > 0 else _DEFAULT_TELEMETRY_RETENTION_DAYS


async def cleanup_expired_telemetry(conn: asyncpg.Connection) -> int:
    """`telemetry_retention_days()`'ten eski `agent_telemetry`
    satırlarını siler, silinen satır sayısını döner. İdempotent —
    tekrar çağırmak güvenli. Henüz hiçbir zamanlayıcı tarafından
    otomatik çağrılmıyor (bkz. `app/db/agents.py::
    delete_expired_telemetry` docstring'i)."""
    return await agents_repo.delete_expired_telemetry(conn, telemetry_retention_days())


def _derive_status(row: dict) -> AgentStatus:
    """`last_heartbeat_at`'ten türetilir — asla DB'de saklanan ayrı bir
    alan değildir (bkz. `app/agents/models.py::AgentStatus`)."""
    last_heartbeat_at: datetime | None = row.get("last_heartbeat_at")
    if last_heartbeat_at is None:
        return "unknown"
    now = datetime.now(timezone.utc)
    if now - last_heartbeat_at > timedelta(seconds=_offline_threshold_seconds()):
        return "offline"
    return "online"


def _latest_available_version(os_name: str) -> str | None:
    """Sunucuda GERÇEKTEN build edilmiş güncel paketin versiyonu —
    yalnızca Windows için (bkz. `app/agents/download.py`, Linux
    packaging henüz yok). Build edilmemişse dürüstçe `None` — asla bir
    versiyon UYDURULMAZ."""
    if os_name != "windows":
        return None
    # Döngüsel import riskini önlemek için burada, kullanım anında
    # import edilir (`app.agents.download` bu modülü hiç import etmez,
    # ama modül-seviyesi import sırası yine de kırılgan olabilir).
    from app.agents.download import ArtifactNotAvailableError, resolve_windows_service_artifact

    try:
        return resolve_windows_service_artifact().version
    except ArtifactNotAvailableError:
        return None


def _to_summary(row: dict) -> AgentSummary:
    latest_version = _latest_available_version(row["os"])
    agent_version = row["agent_version"]
    return AgentSummary(
        id=row["id"],
        hostname=row["hostname"],
        os=row["os"],
        os_version=row.get("os_version"),
        agent_version=agent_version,
        local_ip=row.get("local_ip"),
        asset_id=row.get("asset_id"),
        status=_derive_status(row),
        registered_at=row["registered_at"],
        last_heartbeat_at=row.get("last_heartbeat_at"),
        update_available=latest_version is not None and latest_version != agent_version,
        latest_available_version=latest_version,
    )


async def register_agent(
    conn: asyncpg.Connection, request: AgentRegistrationRequest
) -> AgentRegistrationResponse:
    """Faz 31: kayıt artık geçerli bir `enrollment_code` gerektirir.
    Sıra ÖNEMLİ — önce kod tüketilir (agent henüz YOK), SONRA agent
    oluşturulur, EN SON (yalnızca audit amaçlı) kod↔agent bağlantısı
    kurulur. Bu sıra, geçersiz bir kodun agent oluşturulduktan SONRA
    reddedilip "rogue" bir kayıt bırakmasını yapısal olarak engeller
    (bkz. `app/db/agent_enrollment.py::consume_code` docstring'i)."""
    normalized_code = await enrollment.consume_enrollment_code(conn, request.enrollment_code)

    token = generate_token()
    row = await agents_repo.insert_agent(
        conn,
        hostname=request.hostname,
        fqdn=request.fqdn,
        os=request.os,
        os_version=request.os_version,
        architecture=request.architecture,
        agent_version=request.agent_version,
        local_ip=request.local_ip,
        mac_address=request.mac_address,
        capabilities=request.capabilities,
        token_hash=hash_token(token),
    )
    await enrollment_repo.link_code_to_agent(conn, normalized_code, row["id"])
    return AgentRegistrationResponse(agent_id=row["id"], token=token)


async def create_enrollment_code(conn: asyncpg.Connection) -> dict:
    return await enrollment.create_enrollment_code(conn)


async def list_enrollment_codes(conn: asyncpg.Connection) -> list[dict]:
    return await enrollment.list_active_enrollment_codes(conn)


async def authenticate(conn: asyncpg.Connection, authorization_header: str | None) -> dict:
    """Bearer token'ı doğrular, agent satırını döner. Token eksik,
    formatı yanlış, bilinmiyor VEYA iptal edilmişse — HEPSİ aynı
    `AgentAuthenticationError`'a çevrilir (token'ın var olup olmadığını
    dışarıya sızdırmamak için, timing/enumeration riskini azaltır)."""
    token = extract_bearer_token(authorization_header)
    if not token:
        raise AgentAuthenticationError("Bearer token eksik veya formatı geçersiz")

    row = await agents_repo.get_agent_by_token_hash(conn, hash_token(token))
    if row is None or row.get("revoked_at") is not None:
        raise AgentAuthenticationError("Token geçersiz")
    return row


async def record_heartbeat(
    conn: asyncpg.Connection, agent: dict, uptime_seconds: float | None, agent_version: str | None
) -> AgentSummary:
    row = await agents_repo.update_heartbeat(
        conn,
        agent_id=agent["id"],
        heartbeat_at=datetime.now(timezone.utc),
        uptime_seconds=uptime_seconds,
        agent_version=agent_version,
    )
    if row is None:
        raise AgentNotFoundError(f"Agent bulunamadı: {agent['id']}")
    return _to_summary(row)


async def record_telemetry(
    conn: asyncpg.Connection, agent: dict, request: AgentTelemetryRequest
) -> None:
    await agents_repo.insert_telemetry(
        conn,
        agent_id=agent["id"],
        collected_at=request.collected_at,
        cpu_percent=request.cpu_percent,
        memory_total_bytes=request.memory_total_bytes,
        memory_used_bytes=request.memory_used_bytes,
        memory_percent=request.memory_percent,
        disks=[d.model_dump() for d in request.disks],
        network_interfaces=[n.model_dump(mode="json") for n in request.network_interfaces],
        sessions=[s.model_dump() for s in request.sessions],
        last_logged_in_user=request.last_logged_in_user,
        active_sessions_count=request.active_sessions_count,
    )


async def record_inventory(
    conn: asyncpg.Connection, agent: dict, request: AgentInventoryRequest
) -> None:
    await agents_repo.upsert_inventory(
        conn,
        agent_id=agent["id"],
        hardware=request.hardware.model_dump(mode="json") if request.hardware else None,
        os=request.os.model_dump(mode="json") if request.os else None,
        network_interfaces=[n.model_dump(mode="json") for n in request.network_interfaces],
        software=[s.model_dump() for s in request.software],
        services=[s.model_dump() for s in request.services],
        processes=[p.model_dump() for p in request.processes],
        collected_at=request.collected_at,
    )


async def list_agent_summaries(conn: asyncpg.Connection) -> list[AgentSummary]:
    rows = await agents_repo.list_agents(conn)
    return [_to_summary(row) for row in rows]


async def get_agent_detail(conn: asyncpg.Connection, agent_id: UUID) -> AgentDetail | None:
    row = await agents_repo.get_agent_by_id(conn, agent_id)
    if row is None:
        return None

    telemetry_row = await agents_repo.get_latest_telemetry(conn, agent_id)
    inventory_row = await agents_repo.get_inventory(conn, agent_id)
    latest_version = _latest_available_version(row["os"])

    return AgentDetail(
        id=row["id"],
        hostname=row["hostname"],
        fqdn=row.get("fqdn"),
        os=row["os"],
        os_version=row.get("os_version"),
        agent_version=row["agent_version"],
        asset_id=row.get("asset_id"),
        status=_derive_status(row),
        registered_at=row["registered_at"],
        last_heartbeat_at=row.get("last_heartbeat_at"),
        update_available=latest_version is not None and latest_version != row["agent_version"],
        latest_available_version=latest_version,
        architecture=row.get("architecture"),
        local_ip=row.get("local_ip"),
        mac_address=row.get("mac_address"),
        capabilities=row.get("capabilities") or [],
        revoked_at=row.get("revoked_at"),
        latest_telemetry=AgentTelemetryRequest(
            collected_at=telemetry_row["collected_at"],
            cpu_percent=telemetry_row.get("cpu_percent"),
            memory_total_bytes=telemetry_row.get("memory_total_bytes"),
            memory_used_bytes=telemetry_row.get("memory_used_bytes"),
            memory_percent=telemetry_row.get("memory_percent"),
            disks=telemetry_row.get("disks") or [],
            network_interfaces=telemetry_row.get("network_interfaces") or [],
            sessions=telemetry_row.get("sessions_json") or [],
            last_logged_in_user=telemetry_row.get("last_logged_in_user"),
            active_sessions_count=telemetry_row.get("active_sessions_count"),
        )
        if telemetry_row
        else None,
        inventory=AgentInventoryRequest(
            collected_at=inventory_row["collected_at"],
            hardware=inventory_row.get("hardware"),
            os=inventory_row.get("os"),
            network_interfaces=inventory_row.get("network_interfaces") or [],
            software=inventory_row.get("software") or [],
            services=inventory_row.get("services") or [],
            processes=inventory_row.get("processes") or [],
        )
        if inventory_row
        else None,
    )


def _active_duration_seconds(row: dict) -> float | None:
    """`registered_at` ile agent'ın SON gerçekten aktif olduğu an
    (heartbeat varsa `last_heartbeat_at`, hiç heartbeat yoksa
    arşivlenme anı `archived_at`) arasındaki fark — "ne kadar süre
    aktifti" (Arşiv ekranı). `registered_at` yoksa (olmamalı, NOT NULL
    kolon) dürüstçe `None`."""
    registered_at = row.get("registered_at")
    if registered_at is None:
        return None
    end = row.get("last_heartbeat_at") or row.get("archived_at")
    if end is None:
        return None
    return (end - registered_at).total_seconds()


def _to_archived_summary(row: dict) -> ArchivedAgentSummary:
    return ArchivedAgentSummary(
        id=row["id"],
        hostname=row["hostname"],
        os=row["os"],
        os_version=row.get("os_version"),
        local_ip=row.get("local_ip"),
        registered_at=row["registered_at"],
        last_heartbeat_at=row.get("last_heartbeat_at"),
        archived_at=row["archived_at"],
        archived_reason=row["archived_reason"],
        archived_after_inactive_days=row.get("archived_after_inactive_days"),
        active_duration_seconds=_active_duration_seconds(row),
    )


async def list_archived_agents(conn: asyncpg.Connection) -> list[ArchivedAgentSummary]:
    rows = await agents_repo.list_archived_agents(conn)
    return [_to_archived_summary(row) for row in rows]


async def delete_agent(
    conn: asyncpg.Connection, agent_id: UUID, *, send_uninstall_command: bool
) -> AgentDeleteResult:
    """Manuel silme — Agent'ı ARŞİVLER (kalıcı olarak SİLMEZ, bkz.
    `app/db/agents.py::archive_agent` docstring'i), isteğe bağlı
    olarak arşivlemeden ÖNCE agent'a `uninstall_service` komutu
    kuyruğa alır (agent hâlâ aktifken/token'ı geçerliyken kuyruğa
    girmesi gerekir — arşivleme `revoked_at`'i doldurup kimlik
    doğrulamayı KAPATIR, bu yüzden sıra ÖNEMLİDİR)."""
    from app.agents import command_service
    from app.agents.command_models import AgentCommandRequest

    row = await agents_repo.get_agent_by_id(conn, agent_id)
    if row is None:
        raise AgentNotFoundError(f"Agent bulunamadı: {agent_id}")

    uninstall_command_id: UUID | None = None
    if send_uninstall_command:
        summary = await command_service.submit_command(
            conn,
            agent_id,
            AgentCommandRequest(
                command_type="uninstall_service",
                action="uninstall",
                target="self",
                requested_by="settings-ui",
            ),
        )
        uninstall_command_id = summary.id

    await agents_repo.archive_agent(conn, agent_id, reason="manual")
    return AgentDeleteResult(archived=True, uninstall_command_id=uninstall_command_id)


async def restore_agent(conn: asyncpg.Connection, agent_id: UUID) -> AgentSummary:
    row = await agents_repo.restore_agent(conn, agent_id)
    if row is None:
        raise AgentNotFoundError(f"Agent bulunamadı: {agent_id}")
    return _to_summary(row)


async def get_retention_policy(conn: asyncpg.Connection) -> AgentRetentionPolicy:
    row = await agents_repo.get_retention_policy(conn)
    return AgentRetentionPolicy(enabled=row["enabled"], retention_days=row["retention_days"])


async def set_retention_policy(
    conn: asyncpg.Connection, *, enabled: bool, retention_days: int
) -> AgentRetentionPolicy:
    row = await agents_repo.set_retention_policy(conn, enabled=enabled, retention_days=retention_days)
    return AgentRetentionPolicy(enabled=row["enabled"], retention_days=row["retention_days"])


async def trigger_agent_update(conn: asyncpg.Connection, agent_id: UUID) -> UUID:
    """Uzaktan Sürüm Güncelleme — agent'a `update_self` komutu kuyruğa
    alır, oluşturulan komutun id'sini döner. Agent'ın kendisi henüz
    Windows dışında bu komutu desteklemiyor (bkz. `apps/agent/agent/
    lifecycle.py`) — backend bunu KISITLAMAZ (agent tarafı zaten
    dürüstçe `failed` sonucu bildirir), yalnızca UI `update_available`
    zaten yalnızca Windows için `True` olur."""
    from app.agents import command_service
    from app.agents.command_models import AgentCommandRequest

    agent = await agents_repo.get_agent_by_id(conn, agent_id)
    if agent is None:
        raise AgentNotFoundError(f"Agent bulunamadı: {agent_id}")

    summary = await command_service.submit_command(
        conn,
        agent_id,
        AgentCommandRequest(
            command_type="update_self", action="update", target="self", requested_by="settings-ui"
        ),
    )
    return summary.id


async def evaluate_agent_asset_match(conn: asyncpg.Connection, agent_id: UUID) -> AssetMatchCandidate:
    """Bir agent için mevcut `assets` listesine karşı eşleştirme
    DEĞERLENDİRMESİ döner — hiçbir şey YAZMAZ (bkz. `matching.py`)."""
    agent_row = await agents_repo.get_agent_by_id(conn, agent_id)
    if agent_row is None:
        raise AgentNotFoundError(f"Agent bulunamadı: {agent_id}")
    candidate_assets = await assets_repo.list_assets(conn)
    return evaluate_asset_match(agent_row, candidate_assets)


async def confirm_agent_asset_match(
    conn: asyncpg.Connection, agent_id: UUID, asset_id: UUID
) -> AgentSummary:
    """Bir agent↔asset eşleşmesini AÇIKÇA onaylar (insan/çağıran
    tarafın kararıyla) — `evaluate_agent_asset_match`'in ürettiği bir
    `candidate`/`confirmed` sonucu burada UYGULANIR. Asset gerçekten var
    mı diye kontrol edilir (rastgele bir UUID'ye bağlanmasın diye)."""
    asset_row = await assets_repo.get_asset_by_id(conn, asset_id)
    if asset_row is None:
        raise AgentNotFoundError(f"Asset bulunamadı: {asset_id}")

    row = await agents_repo.set_agent_asset_id(conn, agent_id=agent_id, asset_id=asset_id)
    if row is None:
        raise AgentNotFoundError(f"Agent bulunamadı: {agent_id}")
    return _to_summary(row)
