"""Faz 46 — PAM orkestrasyon katmanı: kasa CRUD (şifreleme/deşifreleme
burada, route katmanında DEĞİL), erişim kuralı CRUD, oturum denetimi
ve zero-knowledge SSH yetkilendirme kontrolü (`authorize_ssh_session`).

**Faz 45'in dersi burada da geçerli:** `assets.ip_address` (INET)
asyncpg'den `ipaddress.IPv4Address` NESNESİ olarak gelir, düz `str`
DEĞİL — bu modüldeki her response dönüşümü `str(row["asset_ip_address"])`
kullanır (`None` ise `None` kalır)."""

from datetime import datetime, timedelta, timezone
from typing import NamedTuple
from uuid import UUID

import asyncpg

from app.db import pam as db
from app.db.ldap import get_group_ids_for_username
from app.db.users import get_user_by_id
from app.pam.models import (
    AccessRequestApproveRequest,
    AccessRequestCreateRequest,
    AccessRequestRejectRequest,
    AccessRequestResponse,
    AuthorizedAssetResponse,
    PamAccessRuleCreateRequest,
    PamAccessRuleResponse,
    PamAccessRuleUpdateRequest,
    PamKeystrokeResponse,
    PamSessionLogResponse,
    ServerGroupCreateRequest,
    ServerGroupResponse,
    ServerGroupUpdateRequest,
    TagCreateRequest,
    TagResponse,
    VaultCredentialCreateRequest,
    VaultCredentialRevealResponse,
    VaultCredentialResponse,
    VaultCredentialUpdateRequest,
)
from app.pam import session_registry
from app.pam.session_registry import request_termination
from app.pam.vault import decrypt_payload, encrypt_payload


class CredentialInUseError(Exception):
    """Kullanılan bir kasa hesabı silinmeye çalışıldığında (bkz. `app/
    db/pam.py::credential_in_use_count`) — sessiz kaskad YOK, mevcut
    Faz 29.5 SNMP profili silme deseniyle aynı `409 Conflict` ilkesi."""


class RuleAlreadyExistsError(Exception):
    """`UNIQUE (user_id, asset_id)` (veya Faz 55'in tag/server_group
    eşdeğerleri) ihlali — Admin mevcut kuralı DÜZENLEMELİ, çakışan
    ikinci bir kural oluşturulamaz."""


class TagInUseError(Exception):
    """En az bir PAM kuralında kullanılan bir etiket silinmeye
    çalışıldığında — sessiz kaskad YOK (bkz. `CredentialInUseError`
    ile AYNI ilke)."""


class ServerGroupInUseError(Exception):
    """`TagInUseError` ile AYNI ilke, cihaz grupları için."""


class AccessRequestNotFoundError(Exception):
    """Verilen `request_id` `pam_access_requests`'te yok."""


class AccessRequestNotPendingError(Exception):
    """Faz 56 — talep zaten onaylanmış/reddedilmiş — `mark_access_
    request_reviewed`'in `WHERE status='pending'` koruması sayesinde
    İKİ admin AYNI ANDA onaylasa/reddetse bile yalnızca biri kazanır,
    diğeri bunu alır (yarış durumuna karşı güvenli)."""


class SshNotAuthorizedError(Exception):
    """`authorize_ssh_session` reddettiğinde — ayrım (kural yok/
    `allow_ssh=false`/süresi dolmuş) çağıran tarafa (`app/routes/
    agent_ssh.py`) sızdırılmaz, hepsi tek bir "yetkisiz" anlamına gelir."""


def _asset_ip(row: asyncpg.Record) -> str | None:
    value = row["asset_ip_address"]
    return str(value) if value is not None else None


def _credential_to_response(row: asyncpg.Record) -> VaultCredentialResponse:
    return VaultCredentialResponse(
        id=row["id"],
        name=row["name"],
        credential_type=row["credential_type"],
        username=row["username"],
        domain=row["domain"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _rule_to_response(row: asyncpg.Record) -> PamAccessRuleResponse:
    return PamAccessRuleResponse(
        id=row["id"],
        user_id=row["user_id"],
        username=row["username"],
        ad_group_id=row["ad_group_id"],
        ad_group_name=row["ad_group_name"],
        asset_id=row["asset_id"],
        asset_hostname=row["asset_hostname"],
        asset_ip_address=_asset_ip(row),
        tag_id=row["tag_id"],
        tag_name=row["tag_name"],
        server_group_id=row["server_group_id"],
        server_group_name=row["server_group_name"],
        credential_id=row["credential_id"],
        credential_name=row["credential_name"],
        allow_rdp=row["allow_rdp"],
        allow_ssh=row["allow_ssh"],
        allow_web=row["allow_web"],
        is_active=row["is_active"],
        max_session_duration_mins=row["max_session_duration_mins"],
        valid_until=row["valid_until"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _session_to_response(row: asyncpg.Record) -> PamSessionLogResponse:
    return PamSessionLogResponse(
        id=row["id"],
        user_id=row["user_id"],
        username=row["username"],
        asset_id=row["asset_id"],
        asset_hostname=row["asset_hostname"],
        asset_ip_address=_asset_ip(row),
        credential_id=row["credential_id"],
        credential_name=row["credential_name"],
        protocol=row["protocol"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        end_reason=row["end_reason"],
        client_ip=row["client_ip"],
        recording_file_path=row["recording_file_path"],
        terminated_by=row["terminated_by"],
    )


# ---- Vault credentials --------------------------------------------------


def _payload_from_create(payload: VaultCredentialCreateRequest) -> dict:
    if payload.credential_type == "password":
        return {"password": payload.password or ""}
    return {"private_key": payload.private_key or "", "passphrase": payload.passphrase}


async def create_credential(conn: asyncpg.Connection, payload: VaultCredentialCreateRequest, *, created_by: UUID) -> VaultCredentialResponse:
    encrypted = encrypt_payload(_payload_from_create(payload))
    row = await db.insert_credential(
        conn,
        name=payload.name,
        credential_type=payload.credential_type,
        username=payload.username,
        domain=payload.domain,
        encrypted_payload=encrypted,
        created_by=created_by,
    )
    return _credential_to_response(row)


async def list_credentials(conn: asyncpg.Connection) -> list[VaultCredentialResponse]:
    rows = await db.list_credentials(conn)
    return [_credential_to_response(row) for row in rows]


async def update_credential(conn: asyncpg.Connection, credential_id: UUID, payload: VaultCredentialUpdateRequest) -> VaultCredentialResponse | None:
    fields_set = payload.model_fields_set
    encrypted_payload = None
    if {"password", "private_key", "passphrase"} & fields_set:
        existing = await db.get_credential(conn, credential_id)
        if existing is None:
            return None
        current = decrypt_payload(existing["encrypted_payload"])
        if existing["credential_type"] == "password":
            if payload.password is not None:
                current["password"] = payload.password
        else:
            if payload.private_key is not None:
                current["private_key"] = payload.private_key
            if "passphrase" in fields_set:
                current["passphrase"] = payload.passphrase
        encrypted_payload = encrypt_payload(current)

    row = await db.update_credential(
        conn,
        credential_id,
        name=payload.name,
        username=payload.username,
        domain_set="domain" in fields_set,
        domain=payload.domain,
        encrypted_payload=encrypted_payload,
    )
    return _credential_to_response(row) if row is not None else None


async def delete_credential(conn: asyncpg.Connection, credential_id: UUID) -> bool:
    in_use = await db.credential_in_use_count(conn, credential_id)
    if in_use > 0:
        raise CredentialInUseError()
    return await db.delete_credential(conn, credential_id)


async def reveal_credential(conn: asyncpg.Connection, credential_id: UUID) -> VaultCredentialRevealResponse | None:
    """Yalnızca route katmanında `require_role("ADMIN")` arkasında
    çağrılmalı — bu fonksiyonun kendisi rol kontrolü yapmaz (bkz. `app/
    routes/pam_vault.py`)."""
    row = await db.get_credential(conn, credential_id)
    if row is None:
        return None
    payload = decrypt_payload(row["encrypted_payload"])
    return VaultCredentialRevealResponse(
        id=row["id"],
        credential_type=row["credential_type"],
        password=payload.get("password"),
        private_key=payload.get("private_key"),
        passphrase=payload.get("passphrase"),
    )


# ---- Access rules ---------------------------------------------------------


async def create_rule(conn: asyncpg.Connection, payload: PamAccessRuleCreateRequest, *, created_by: UUID) -> PamAccessRuleResponse:
    # Faz 49/55 — `payload`'ın Pydantic validator'ı principal (user_id/
    # ad_group_id) VE cihaz hedefinin (asset_id/tag_id/server_group_id)
    # HER İKİSİ için de TAM OLARAK biri dolu olmasını zaten garanti
    # ediyor. Tekrar/duplikasyon kontrolü artık PROAKTIF bir SELECT ile
    # DEĞİL — 6 (principal × cihaz hedefi) kombinasyonu için 6 ayrı
    # ön-kontrol sorgusu yazmak yerine, `infra/postgres/init.sql`'deki
    # gerçek UNIQUE kısıtlarına güveniliyor (bkz. `app/db/pam.py::
    # insert_rule` docstring'i).
    try:
        row = await db.insert_rule(
            conn,
            user_id=payload.user_id,
            ad_group_id=payload.ad_group_id,
            asset_id=payload.asset_id,
            tag_id=payload.tag_id,
            server_group_id=payload.server_group_id,
            credential_id=payload.credential_id,
            allow_rdp=payload.allow_rdp,
            allow_ssh=payload.allow_ssh,
            allow_web=payload.allow_web,
            max_session_duration_mins=payload.max_session_duration_mins,
            valid_until=payload.valid_until,
            created_by=created_by,
        )
    except asyncpg.UniqueViolationError as exc:
        raise RuleAlreadyExistsError() from exc
    return _rule_to_response(row)


async def list_rules(
    conn: asyncpg.Connection, *, search: str | None = None, limit: int | None = None, offset: int | None = None
) -> list[PamAccessRuleResponse]:
    rows = await db.list_rules(conn, search=search, limit=limit, offset=offset)
    return [_rule_to_response(row) for row in rows]


# ---- Faz 55 — Cihaz Etiketleri (Tags) + Statik Cihaz Grupları -------------


def _tag_to_response(row: asyncpg.Record) -> TagResponse:
    return TagResponse(id=row["id"], name=row["name"], created_at=row["created_at"])


async def create_tag(conn: asyncpg.Connection, payload: TagCreateRequest, *, created_by: UUID) -> TagResponse:
    row = await db.insert_tag(conn, name=payload.name, created_by=created_by)
    return _tag_to_response(row)


async def list_tags(conn: asyncpg.Connection) -> list[TagResponse]:
    return [_tag_to_response(row) for row in await db.list_tags(conn)]


async def delete_tag(conn: asyncpg.Connection, tag_id: UUID) -> bool:
    if await db.tag_rule_count(conn, tag_id) > 0:
        raise TagInUseError()
    return await db.delete_tag(conn, tag_id)


async def assign_tag(conn: asyncpg.Connection, *, tag_id: UUID, asset_id: UUID) -> None:
    await db.assign_tag(conn, asset_id=asset_id, tag_id=tag_id)


async def unassign_tag(conn: asyncpg.Connection, *, tag_id: UUID, asset_id: UUID) -> None:
    await db.unassign_tag(conn, asset_id=asset_id, tag_id=tag_id)


async def list_assets_for_tag(conn: asyncpg.Connection, tag_id: UUID) -> list[asyncpg.Record]:
    return await db.list_assets_for_tag(conn, tag_id)


def _server_group_to_response(row: asyncpg.Record) -> ServerGroupResponse:
    return ServerGroupResponse(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def create_server_group(
    conn: asyncpg.Connection, payload: ServerGroupCreateRequest, *, created_by: UUID
) -> ServerGroupResponse:
    row = await db.insert_server_group(conn, name=payload.name, description=payload.description, created_by=created_by)
    return _server_group_to_response(row)


async def list_server_groups(conn: asyncpg.Connection) -> list[ServerGroupResponse]:
    return [_server_group_to_response(row) for row in await db.list_server_groups(conn)]


async def update_server_group(
    conn: asyncpg.Connection, server_group_id: UUID, payload: ServerGroupUpdateRequest
) -> ServerGroupResponse | None:
    fields_set = payload.model_fields_set
    row = await db.update_server_group(
        conn,
        server_group_id,
        name=payload.name,
        description=payload.description,
        description_set="description" in fields_set,
    )
    return _server_group_to_response(row) if row is not None else None


async def delete_server_group(conn: asyncpg.Connection, server_group_id: UUID) -> bool:
    if await db.server_group_rule_count(conn, server_group_id) > 0:
        raise ServerGroupInUseError()
    return await db.delete_server_group(conn, server_group_id)


async def add_group_member(conn: asyncpg.Connection, *, server_group_id: UUID, asset_id: UUID) -> None:
    await db.add_group_member(conn, server_group_id=server_group_id, asset_id=asset_id)


async def remove_group_member(conn: asyncpg.Connection, *, server_group_id: UUID, asset_id: UUID) -> None:
    await db.remove_group_member(conn, server_group_id=server_group_id, asset_id=asset_id)


async def list_assets_for_group(conn: asyncpg.Connection, server_group_id: UUID) -> list[asyncpg.Record]:
    return await db.list_assets_for_group(conn, server_group_id)


async def update_rule(conn: asyncpg.Connection, rule_id: UUID, payload: PamAccessRuleUpdateRequest) -> PamAccessRuleResponse | None:
    fields_set = payload.model_fields_set
    row = await db.update_rule(
        conn,
        rule_id,
        credential_id=payload.credential_id,
        allow_rdp=payload.allow_rdp,
        allow_ssh=payload.allow_ssh,
        allow_web=payload.allow_web,
        is_active=payload.is_active,
        max_session_duration_mins=payload.max_session_duration_mins,
        valid_until_set="valid_until" in fields_set,
        valid_until=payload.valid_until,
    )
    return _rule_to_response(row) if row is not None else None


async def delete_rule(conn: asyncpg.Connection, rule_id: UUID) -> bool:
    return await db.delete_rule(conn, rule_id)


async def list_authorized_assets_for_user(conn: asyncpg.Connection, user_id: UUID) -> list[AuthorizedAssetResponse]:
    """OPERATOR/VIEWER'ın kendi `GET /api/pam/my-access`'i — süresi
    dolmuş kurallar dürüstçe hiç dönmez (kullanıcı "yetkin var ama
    süresi doldu" belirsizliği yaşamaz, liste basitçe onu içermez).

    Faz 49 — DOĞRUDAN yerel kurallara EK olarak, kullanıcı bir AD
    hesabına bağlıysa (`users.ad_username`) o hesabın ÜYE OLDUĞU AD
    gruplarından gelen kurallar da dahil edilir. Aynı asset için hem
    doğrudan hem grup kuralı varsa DOĞRUDAN kural KAZANIR (daha
    spesifik/kasıtlı bir atama olduğu için).

    Faz 55 — cihaz hedefi de artık üç kademeli: cihaz grubu < etiket <
    doğrudan asset (aynı "en spesifik kazanır" ilkesi) — altı liste de
    EN DÜŞÜK öncelikliden EN YÜKSEK öncelikliye sırayla `rows_by_asset`
    dict'ine yazılır, her sonraki yazma bir ÖNCEKİNİN üzerine geçer."""
    now = datetime.now(timezone.utc)
    rows_by_asset: dict[UUID, asyncpg.Record] = {}
    ad_group_ids = await _ad_group_ids_for_user(conn, user_id)

    for row in await db.list_group_rules_expanded_for_ad_groups(conn, ad_group_ids):
        rows_by_asset[row["asset_id"]] = row
    for row in await db.list_tag_rules_expanded_for_ad_groups(conn, ad_group_ids):
        rows_by_asset[row["asset_id"]] = row
    for row in await db.list_rules_for_ad_groups(conn, ad_group_ids):
        rows_by_asset[row["asset_id"]] = row
    for row in await db.list_group_rules_expanded_for_user(conn, user_id):
        rows_by_asset[row["asset_id"]] = row
    for row in await db.list_tag_rules_expanded_for_user(conn, user_id):
        rows_by_asset[row["asset_id"]] = row
    for row in await db.list_rules_for_user(conn, user_id):
        rows_by_asset[row["asset_id"]] = row  # doğrudan kural her zaman EN SON, en yüksek öncelik

    active_counts = await _active_session_counts_by_asset(conn)

    return [
        AuthorizedAssetResponse(
            asset_id=row["asset_id"],
            asset_hostname=row["asset_hostname"],
            asset_ip_address=_asset_ip(row),
            allow_rdp=row["allow_rdp"],
            allow_ssh=row["allow_ssh"],
            allow_web=row["allow_web"],
            max_session_duration_mins=row["max_session_duration_mins"],
            valid_until=row["valid_until"],
            is_online=row["asset_status"] == "up",
            active_sessions_count=active_counts.get(row["asset_id"], 0),
        )
        for row in rows_by_asset.values()
        if row["is_active"] and (row["valid_until"] is None or row["valid_until"] > now)
    ]


async def _active_session_counts_by_asset(conn: asyncpg.Connection) -> dict[UUID, int]:
    """Faz 58 — "Aktif Oturumlar" rozeti için, asset_id başına GERÇEKTEN
    aktif (Faz 51'in `session_registry` çapraz kontrolünden geçmiş)
    oturum sayısı. Yeni bir sayaç/tablo AÇILMAZ — `list_session_logs`'un
    ZATEN kendi kendini düzelten `active_only=True` mantığı reuse
    edilir (bkz. o fonksiyonun docstring'i)."""
    active_sessions = await list_session_logs(conn, active_only=True)
    counts: dict[UUID, int] = {}
    for session in active_sessions:
        counts[session.asset_id] = counts.get(session.asset_id, 0) + 1
    return counts


async def _ad_group_ids_for_user(conn: asyncpg.Connection, user_id: UUID) -> list[UUID]:
    """`users.ad_username` bağlıysa o AD hesabının DOĞRUDAN üyesi
    olduğu grupların id listesi, bağlı değilse boş liste."""
    user_row = await get_user_by_id(conn, user_id)
    if user_row is None or not user_row["ad_username"]:
        return []
    return await get_group_ids_for_username(conn, user_row["ad_username"])


# ---- Zero-knowledge SSH yetkilendirme --------------------------------------


async def _resolve_rule(conn: asyncpg.Connection, *, user_id: UUID, asset_id: UUID) -> asyncpg.Record | None:
    """Faz 49 — ÖNCE doğrudan yerel kural, YOKSA (kullanıcı bir AD
    hesabına bağlıysa) o hesabın AD grup üyeliklerinden gelen kural.
    Doğrudan kural her zaman ÖNCELİKLİDİR (bkz. `list_authorized_
    assets_for_user`'daki aynı ilke). Faz 55 — "doğrudan kural" artık
    yalnızca asset-hedefli DEĞİL, `get_device_rule_for_user`'ın kendisi
    zaten etiket/grup kurallarını da (asset > tag > group önceliğiyle)
    çözüyor."""
    rule = await db.get_device_rule_for_user(conn, user_id, asset_id)
    if rule is not None:
        return rule
    return await db.get_device_rule_for_ad_groups(conn, await _ad_group_ids_for_user(conn, user_id), asset_id)


async def authorize_ssh_session(conn: asyncpg.Connection, *, user_id: UUID, asset_id: UUID) -> tuple[str, dict, int, UUID]:
    """PAM-yetkili bir SSH bağlantısı açmadan ÖNCE çağrılır (bkz. `app/
    routes/agent_ssh.py`). Yetkiliyse `(host_username, decrypted_secret_
    payload, max_session_duration_mins, credential_id)` döner — kimlik
    bilgisi DEĞERİ yalnızca burada, çağrının kendi stack frame'inde
    çözülür, hiçbir zaman HTTP response'una/websocket'e/log'a yazılmaz.
    Yetkisizse `SshNotAuthorizedError` (401/403'e çevrilir, ayrım
    sızdırılmaz)."""
    rule = await _resolve_rule(conn, user_id=user_id, asset_id=asset_id)
    if rule is None or not rule["is_active"] or not rule["allow_ssh"]:
        raise SshNotAuthorizedError()
    if rule["valid_until"] is not None and rule["valid_until"] <= datetime.now(timezone.utc):
        raise SshNotAuthorizedError()

    credential = await db.get_credential(conn, rule["credential_id"])
    if credential is None:
        raise SshNotAuthorizedError()

    payload = decrypt_payload(credential["encrypted_payload"])
    return credential["username"], payload, rule["max_session_duration_mins"], credential["id"]


# ---- RDP (Faz 48 — Guacamole/guacd üzerinden gerçek zero-knowledge) -------


class RdpConnectionAuthorization(NamedTuple):
    """`authorize_rdp_session`'ın döndürdüğü, guacd el sıkışması için
    gereken TÜM alanlar — `password` DAHİL (Faz 47'nin YALNIZCA
    kullanıcı adı döndüren `.rdp`-dosyası akışının YERİNE geçti, bkz.
    docs/roadmap.md Faz 48 notu)."""

    username: str
    password: str | None
    domain: str | None
    max_session_duration_mins: int
    credential_id: UUID


async def authorize_rdp_session(conn: asyncpg.Connection, *, user_id: UUID, asset_id: UUID) -> RdpConnectionAuthorization:
    """PAM-yetkili bir GERÇEK RDP oturumu (guacd üzerinden) açmadan ÖNCE
    çağrılır (bkz. `app/routes/pam_rdp.py`). Kasadaki kimlik bilgisi
    burada, çağıranın kendi stack frame'inde çözülür ve YALNIZCA guacd'ye
    (sunucu-sunucu TCP) geçirilir — tarayıcıya hiçbir zaman gönderilmez.
    Yetkisizse `SshNotAuthorizedError` (isim SSH'a özel değil, "PAM
    bağlantı yetkisizliği" anlamında paylaşılıyor — ayrı bir exception
    sınıfı açmak gereksiz bir soyutlama olurdu)."""
    rule = await _resolve_rule(conn, user_id=user_id, asset_id=asset_id)
    if rule is None or not rule["is_active"] or not rule["allow_rdp"]:
        raise SshNotAuthorizedError()
    if rule["valid_until"] is not None and rule["valid_until"] <= datetime.now(timezone.utc):
        raise SshNotAuthorizedError()

    credential = await db.get_credential(conn, rule["credential_id"])
    if credential is None:
        raise SshNotAuthorizedError()

    payload = decrypt_payload(credential["encrypted_payload"])
    return RdpConnectionAuthorization(
        username=credential["username"],
        password=payload.get("password"),
        domain=credential["domain"],
        max_session_duration_mins=rule["max_session_duration_mins"],
        credential_id=credential["id"],
    )


# ---- Web Konsolu (Faz 76 — zero-knowledge HTTPS kimlik enjeksiyonu) -------


class WebConsoleNotConfiguredError(Exception):
    """Kural `allow_web=true` olsa bile bu asset için hiç `pam_web_
    console_profiles` satırı yoksa — Admin'in önce cihazın giriş
    formu alanlarını yapılandırması gerekir (bkz. docs/roadmap.md
    Faz 76 — kod içine sabit bir şema UYDURULMADI)."""


class WebConsoleAuthorization(NamedTuple):
    username: str
    password: str
    profile: asyncpg.Record
    max_session_duration_mins: int
    credential_id: UUID


async def authorize_web_session(conn: asyncpg.Connection, *, user_id: UUID, asset_id: UUID) -> WebConsoleAuthorization:
    """PAM-yetkili bir web konsolu oturumu açmadan ÖNCE çağrılır (bkz.
    `app/routes/pam_web.py`). `authorize_rdp_session` ile AYNI
    yetkilendirme sırası + AYRICA bu asset için gerçekten yapılandırılmış
    bir `pam_web_console_profiles` satırı arar."""
    rule = await _resolve_rule(conn, user_id=user_id, asset_id=asset_id)
    if rule is None or not rule["is_active"] or not rule["allow_web"]:
        raise SshNotAuthorizedError()
    if rule["valid_until"] is not None and rule["valid_until"] <= datetime.now(timezone.utc):
        raise SshNotAuthorizedError()

    profile = await db.get_web_console_profile(conn, asset_id)
    if profile is None:
        raise WebConsoleNotConfiguredError()

    credential = await db.get_credential(conn, rule["credential_id"])
    if credential is None:
        raise SshNotAuthorizedError()

    payload = decrypt_payload(credential["encrypted_payload"])
    password = payload.get("password")
    if password is None:
        # `credential_type='ssh_key'` bir kasa hesabı web konsolu için
        # ANLAMSIZ (parola alanı yok) — dürüstçe yetkisiz say.
        raise SshNotAuthorizedError()

    return WebConsoleAuthorization(
        username=credential["username"],
        password=password,
        profile=profile,
        max_session_duration_mins=rule["max_session_duration_mins"],
        credential_id=credential["id"],
    )


# ---- Audit -----------------------------------------------------------------


async def list_session_logs(
    conn: asyncpg.Connection,
    *,
    active_only: bool,
    search: str | None = None,
    protocol: str | None = None,
    reason: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[PamSessionLogResponse]:
    rows = await db.list_session_logs(
        conn, active_only=active_only, search=search, protocol=protocol, reason=reason, limit=limit, offset=offset
    )
    if active_only:
        # Faz 51 — gerçek bir durum senkronizasyon bug'ı bulunup
        # düzeltildi: `ended_at IS NULL` TEK BAŞINA "canlı" için
        # yeterli değil — WebSocket köprüsü (bkz. `app/routes/pam_rdp.
        # py`/`pam_ssh.py`) `session_registry.unregister()`'ı HER
        # zaman (try/finally ile) çalıştırır, ama onu izleyen `close_
        # session_log` DB yazımı (ör. geçici bir bağlantı sorunu
        # yüzünden) başarısız olursa satır DB'de sonsuza kadar
        # `ended_at IS NULL` görünüp "Canlı Oturumlar" listesinde
        # kalıcı bir hayalet olarak kalabilirdi. Bu SÜREÇTEKİ gerçek
        # kaynağa (`session_registry`) karşı çapraz kontrol, DB
        # yazımı başarısız olsa bile listenin kendi kendini
        # düzeltmesini sağlar.
        rows = [row for row in rows if session_registry.is_active(row["id"])]
    return [_session_to_response(row) for row in rows]


class SessionNotFoundError(Exception):
    """Verilen `session_id` `pam_session_logs`'ta yok."""


class SessionNotActiveError(Exception):
    """Faz 50 — `terminate_session` bir oturumu bu SÜREÇTE aktif
    (bkz. `app/pam/session_registry.py`) BULAMADIĞINDA: oturum zaten
    kendiliğinden kapanmış OLABİLİR, ya da backend bu oturum
    başladıktan SONRA yeniden başlatılmış olabilir (bellek-içi registry
    süreç ömrüyle sınırlı) — ikisi de aynı "artık canlı değil" anlamına
    geldiği için ayrım sızdırılmaz."""


async def terminate_session(conn: asyncpg.Connection, session_id: UUID, *, terminated_by: UUID) -> PamSessionLogResponse:
    """Admin'in "Oturumu Anında Kapat" eylemi — WebSocket köprüsüne
    (bkz. `app/pam/session_registry.py::request_termination`) bir kill
    sinyali gönderir. Köprünün KENDİSİ bunu görüp `pam_session_logs`'u
    `end_reason="terminated_by_admin"` ile kapatır (bkz. `app/routes/
    pam_rdp.py`/`pam_ssh.py`) — bu fonksiyon DB satırını DOĞRUDAN
    kapatmaz, yalnızca sinyali gönderir ve GÜNCEL satırı döner (köprü
    henüz kapanmamış olabileceği için satır hâlâ `ended_at IS NULL`
    gösterebilir; admin panelindeki liste bir sonraki yenilemede
    gerçek kapanışı yansıtır)."""
    row = await db.get_session_log(conn, session_id)
    if row is None:
        raise SessionNotFoundError()
    if row["ended_at"] is not None:
        raise SessionNotActiveError()
    # `terminated_by` kill event SET EDİLMEDEN ÖNCE yazılır — admin
    # kimliği yalnızca BURADA (istek sırasında) biliniyor; WebSocket
    # köprüsü daha sonra `end_reason`/`ended_at`'ı yazarken bu kolona
    # dokunmaz (bkz. `app/db/pam.py::close_session_log`).
    await db.mark_termination_requested(conn, session_id, terminated_by)
    if not request_termination(session_id):
        raise SessionNotActiveError()
    row = await db.get_session_log(conn, session_id)
    return _session_to_response(row)


async def list_keystrokes(conn: asyncpg.Connection, session_id: UUID) -> list[PamKeystrokeResponse]:
    if await db.get_session_log(conn, session_id) is None:
        raise SessionNotFoundError()
    rows = await db.list_keystrokes(conn, session_id)
    return [PamKeystrokeResponse(id=row["id"], recorded_at=row["recorded_at"], data=row["data"]) for row in rows]


# ---- Faz 56 — Erişim Talepleri (Access Requests) --------------------------


def _access_request_to_response(row: asyncpg.Record) -> AccessRequestResponse:
    return AccessRequestResponse(
        id=row["id"],
        requester_id=row["requester_id"],
        requester_username=row["requester_username"],
        asset_id=row["asset_id"],
        asset_hostname=row["asset_hostname"],
        asset_ip_address=_asset_ip(row),
        tag_id=row["tag_id"],
        tag_name=row["tag_name"],
        server_group_id=row["server_group_id"],
        server_group_name=row["server_group_name"],
        protocol=row["protocol"],
        business_reason=row["business_reason"],
        requested_duration_mins=row["requested_duration_mins"],
        status=row["status"],
        reviewed_by=row["reviewed_by"],
        reviewed_by_username=row["reviewed_by_username"],
        reviewed_at=row["reviewed_at"],
        review_note=row["review_note"],
        created_at=row["created_at"],
    )


async def create_access_request(
    conn: asyncpg.Connection, payload: AccessRequestCreateRequest, *, requester_id: UUID
) -> AccessRequestResponse:
    row = await db.insert_access_request(
        conn,
        requester_id=requester_id,
        asset_id=payload.asset_id,
        tag_id=payload.tag_id,
        server_group_id=payload.server_group_id,
        protocol=payload.protocol,
        business_reason=payload.business_reason,
        requested_duration_mins=payload.requested_duration_mins,
    )
    return _access_request_to_response(row)


async def list_access_requests(
    conn: asyncpg.Connection, *, status: str | None = None, requester_id: UUID | None = None
) -> list[AccessRequestResponse]:
    rows = await db.list_access_requests(conn, status=status, requester_id=requester_id)
    return [_access_request_to_response(row) for row in rows]


async def reject_access_request(
    conn: asyncpg.Connection, request_id: UUID, payload: AccessRequestRejectRequest, *, reviewed_by: UUID
) -> AccessRequestResponse:
    if await db.get_access_request(conn, request_id) is None:
        raise AccessRequestNotFoundError()
    row = await db.mark_access_request_reviewed(
        conn, request_id, status="rejected", reviewed_by=reviewed_by, review_note=payload.review_note
    )
    if row is None:
        raise AccessRequestNotPendingError()
    return _access_request_to_response(row)


async def approve_access_request(
    conn: asyncpg.Connection, request_id: UUID, payload: AccessRequestApproveRequest, *, reviewed_by: UUID
) -> AccessRequestResponse:
    """Faz 56'nın merkezi fonksiyonu — YENİ bir yetkilendirme mekanizması
    YAZMAZ, mevcut `pam_access_rules`'u (Faz 46-55) GENİŞLETİR/OLUŞTURUR.
    Önce durum geçişini (`pending`→`approved`) ATOMİK olarak dener —
    bu BAŞARISIZ olursa (talep bulunamadı/zaten incelenmiş) hiçbir
    kural değişikliği YAPILMAZ; başarılı olursa GERÇEK erişim
    materialize edilir."""
    request_row = await db.get_access_request(conn, request_id)
    if request_row is None:
        raise AccessRequestNotFoundError()

    updated_request = await db.mark_access_request_reviewed(
        conn, request_id, status="approved", reviewed_by=reviewed_by, review_note=payload.review_note
    )
    if updated_request is None:
        raise AccessRequestNotPendingError()

    requested_protocol = request_row["protocol"]
    new_valid_until = datetime.now(timezone.utc) + timedelta(minutes=request_row["requested_duration_mins"])

    existing_rule = await db.get_rule_for_exact_user_target(
        conn,
        request_row["requester_id"],
        asset_id=request_row["asset_id"],
        tag_id=request_row["tag_id"],
        server_group_id=request_row["server_group_id"],
    )
    if existing_rule is not None:
        # Mevcut kuralı GENİŞLET: izin bayrağını EKLE (var olanı
        # KAPATMA), geçerlilik süresini UZAT (zaten süresizse veya
        # istenenden daha uzunsa KISALTMA).
        if existing_rule["valid_until"] is None:
            merged_valid_until = None
        elif existing_rule["valid_until"] < new_valid_until:
            merged_valid_until = new_valid_until
        else:
            merged_valid_until = existing_rule["valid_until"]
        await db.update_rule(
            conn,
            existing_rule["id"],
            credential_id=payload.credential_id,
            allow_rdp=existing_rule["allow_rdp"] or requested_protocol == "rdp",
            allow_ssh=existing_rule["allow_ssh"] or requested_protocol == "ssh",
            # Faz 76 — erişim talepleri hâlâ yalnızca ssh/rdp seçebiliyor
            # (`pam_access_requests.protocol` CHECK'i genişletilmedi,
            # bkz. docs/roadmap.md Faz 76 kapsam dışı) — `None` mevcut
            # `allow_web` değerini KORUR, üzerine yazmaz.
            allow_web=None,
            is_active=True,
            max_session_duration_mins=None,
            valid_until_set=True,
            valid_until=merged_valid_until,
        )
    else:
        # Yeni bir kural aç — `requested_duration_mins` HEM geçerlilik
        # penceresini (`valid_until`) HEM tek bir oturumun üst sınırını
        # (`max_session_duration_mins`) belirler: kullanıcının isteğinde
        # ayrı bir "oturum başına süre" alanı YOK, ikisini AYNI değere
        # bağlamak (talep edilenden daha uzun bir tek oturum, mantıksal
        # bir tutarsızlık olurdu) en basit/en dürüst varsayılan.
        await db.insert_rule(
            conn,
            user_id=request_row["requester_id"],
            ad_group_id=None,
            asset_id=request_row["asset_id"],
            tag_id=request_row["tag_id"],
            server_group_id=request_row["server_group_id"],
            credential_id=payload.credential_id,
            allow_rdp=requested_protocol == "rdp",
            allow_ssh=requested_protocol == "ssh",
            allow_web=False,
            max_session_duration_mins=request_row["requested_duration_mins"],
            valid_until=new_valid_until,
            created_by=reviewed_by,
        )

    return _access_request_to_response(updated_request)
