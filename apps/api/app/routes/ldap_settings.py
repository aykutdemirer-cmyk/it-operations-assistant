"""Faz 49 — `/api/settings/ldap`: LDAP/Active Directory yapılandırması +
dizin senkronizasyonu. `PAM_ADMIN` gerektirir — `vault_credentials`
gibi hassas bir bağlantı bilgisi (bind parolası) taşıdığı için PAM'in
diğer yönetim ekranlarıyla AYNI yetki sınırında."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import require_permission
from app.db.ldap import get_config, get_connection, list_groups, list_users, record_sync_result, upsert_config
from app.services.ldap import LdapConnectError, LdapConnectionParams, decrypt_bind_password, encrypt_bind_password, sync_directory, test_connection
from app.services.ldap_models import (
    AdGroupResponse,
    AdUserResponse,
    LdapConfigRequest,
    LdapConfigResponse,
    LdapSyncResult,
    LdapTestResult,
)

router = APIRouter(prefix="/api/settings/ldap", tags=["ldap"], dependencies=[Depends(require_permission("PAM_ADMIN"))])

logger = logging.getLogger(__name__)


async def _connect():
    try:
        return await get_connection()
    except OSError as exc:
        logger.warning("PostgreSQL erişilemedi (ldap settings)")
        raise HTTPException(status_code=503, detail={"database": "unreachable"}) from exc


def _to_response(row) -> LdapConfigResponse:
    return LdapConfigResponse(
        host=row["host"],
        port=row["port"],
        use_ssl=row["use_ssl"],
        domain_fqdn=row["domain_fqdn"],
        base_dn=row["base_dn"],
        bind_dn=row["bind_dn"],
        last_sync_status=row["last_sync_status"],
        last_sync_error=row["last_sync_error"],
        last_sync_at=row["last_sync_at"],
        updated_at=row["updated_at"],
    )


def _connection_params(payload: LdapConfigRequest, *, bind_password: str) -> LdapConnectionParams:
    return {
        "host": payload.host,
        "port": payload.port,
        "use_ssl": payload.use_ssl,
        "domain_fqdn": payload.domain_fqdn,
        "bind_dn": payload.bind_dn,
        "bind_password": bind_password,
        "base_dn": payload.base_dn,
    }


@router.get("", response_model=LdapConfigResponse | None)
async def get_ldap_config_route() -> LdapConfigResponse | None:
    conn = await _connect()
    try:
        row = await get_config(conn)
    finally:
        await conn.close()
    return _to_response(row) if row is not None else None


async def _existing_config_or_422(conn) -> object:
    existing = await get_config(conn)
    if existing is None:
        raise HTTPException(status_code=422, detail="Bind parolası ilk kayıtta zorunludur")
    return existing


async def _resolve_bind_password(conn, payload: LdapConfigRequest) -> str:
    """`payload.bind_password` doluysa (kullanıcı gerçekten yeni bir
    parola girdiyse) onu kullanır — boşsa/`None` ise (Vault kimlik
    bilgisi güncellemesiyle AYNI ilke: "bu alanı değiştirme") KAYITLI
    yapılandırmadaki mevcut şifreli parolayı çözüp DÜZ METİN olarak
    döner — `test_connection`'ın ihtiyacı bu (bkz. `_resolve_encrypted_
    bind_password`, `PUT` için AYNI amaca hizmet eden ama gereksiz bir
    decrypt+reencrypt turu YAPMAYAN kardeşi)."""
    if payload.bind_password:
        return payload.bind_password
    existing = await _existing_config_or_422(conn)
    return decrypt_bind_password(existing["encrypted_bind_password"])


async def _resolve_encrypted_bind_password(conn, payload: LdapConfigRequest) -> str:
    """`PUT`'a özel: parola boş bırakılırsa KAYITLI şifreli değeri
    decrypt+reencrypt YAPMADAN, olduğu gibi (aynı Fernet baytları)
    korur — `app/pam/service.py::update_credential`'ın `encrypted_
    payload = None` → `COALESCE` deseniyle AYNI ilke, gereksiz bir
    decrypt/reencrypt turundan kaçınır (Fernet non-deterministik
    olduğu için her reencrypt farklı ciphertext üretir — anlamca aynı
    olsa da denetlenebilirlik açısından "değiştirilmedi" gerçeğini
    bayt düzeyinde de yansıtmak daha doğru)."""
    if payload.bind_password:
        return encrypt_bind_password(payload.bind_password)
    existing = await _existing_config_or_422(conn)
    return existing["encrypted_bind_password"]


@router.put("", response_model=LdapConfigResponse)
async def update_ldap_config_route(payload: LdapConfigRequest) -> LdapConfigResponse:
    conn = await _connect()
    try:
        encrypted_bind_password = await _resolve_encrypted_bind_password(conn, payload)
        row = await upsert_config(
            conn,
            host=payload.host,
            port=payload.port,
            use_ssl=payload.use_ssl,
            domain_fqdn=payload.domain_fqdn,
            base_dn=payload.base_dn,
            bind_dn=payload.bind_dn,
            encrypted_bind_password=encrypted_bind_password,
        )
    finally:
        await conn.close()
    return _to_response(row)


@router.post("/test", response_model=LdapTestResult)
async def test_ldap_connection_route(payload: LdapConfigRequest) -> LdapTestResult:
    """Girilen (henüz KAYDEDİLMEMİŞ olabilecek) parametrelerle GERÇEK
    bir LDAP bağlantısı/bind dener — kullanıcının "Bağlantıyı Test Et"
    butonu. Bind parolası boş bırakılırsa (`_resolve_bind_password`)
    KAYITLI yapılandırmanın parolasıyla test eder — host/port gibi
    diğer alanları değiştirip parolayı yeniden yazmadan da test
    edilebilsin diye. Başarısızlıkta 4xx/5xx YERİNE `success=false`
    döner (SNMP "Test Connection" ile AYNI ilke — bir bağlantı
    denemesinin BAŞARISIZ olması bir API hatası değildir, dürüst bir
    sonuçtur)."""
    conn = await _connect()
    try:
        bind_password = await _resolve_bind_password(conn, payload)
    finally:
        await conn.close()
    try:
        await test_connection(_connection_params(payload, bind_password=bind_password))
        return LdapTestResult(success=True, message="Bağlantı başarılı")
    except LdapConnectError as exc:
        return LdapTestResult(success=False, message=str(exc))


@router.post("/sync", response_model=LdapSyncResult)
async def sync_ldap_directory_route() -> LdapSyncResult:
    """KAYITLI yapılandırmayla GERÇEK bir dizin senkronizasyonu yapar —
    "Şimdi Senkronize Et" butonu. Önce config KAYDEDİLMİŞ olmalı (bkz.
    `PUT`) — test etmek/senkronize etmek AYRI adımlar."""
    conn = await _connect()
    try:
        row = await get_config(conn)
        if row is None:
            raise HTTPException(status_code=409, detail="Önce LDAP yapılandırması kaydedilmeli")

        params: LdapConnectionParams = {
            "host": row["host"],
            "port": row["port"],
            "use_ssl": row["use_ssl"],
            "domain_fqdn": row["domain_fqdn"],
            "bind_dn": row["bind_dn"],
            "bind_password": decrypt_bind_password(row["encrypted_bind_password"]),
            "base_dn": row["base_dn"],
        }
        try:
            result = await sync_directory(conn, params)
        except LdapConnectError as exc:
            await record_sync_result(conn, status="error", error=str(exc))
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        await record_sync_result(conn, status="success", error=None)
        return LdapSyncResult(
            groups_synced=result.groups_synced,
            users_synced=result.users_synced,
            memberships_synced=result.memberships_synced,
        )
    finally:
        await conn.close()


@router.get("/groups", response_model=list[AdGroupResponse])
async def list_ad_groups_route() -> list[AdGroupResponse]:
    """PAM kural ekranındaki "AD Grupları" açılır listesinin veri
    kaynağı — yalnızca EN SON senkronizasyonda görülen gruplar."""
    conn = await _connect()
    try:
        rows = await list_groups(conn)
    finally:
        await conn.close()
    return [
        AdGroupResponse(id=row["id"], distinguished_name=row["distinguished_name"], name=row["name"], synced_at=row["synced_at"])
        for row in rows
    ]


@router.get("/users", response_model=list[AdUserResponse])
async def list_ad_users_route() -> list[AdUserResponse]:
    """Faz 52 — `/pam/users`'ın "Active Directory'den İçe Aktar"
    seçicisinin veri kaynağı — yalnızca EN SON senkronizasyonda görülen
    kullanıcılar."""
    conn = await _connect()
    try:
        rows = await list_users(conn)
    finally:
        await conn.close()
    return [
        AdUserResponse(
            id=row["id"],
            distinguished_name=row["distinguished_name"],
            username=row["username"],
            display_name=row["display_name"],
            email=row["email"],
            synced_at=row["synced_at"],
        )
        for row in rows
    ]
