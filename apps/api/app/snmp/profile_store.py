"""Bir asset için `SNMPProfile` çözümleme.

Henüz kalıcı bir credential/profile tablosu YOK (bilinçli karar — bkz.
`credentials.py` docstring'i ve `docs/decisions.md` §10/§10.2: gerçek bir
SNMP ajanı/cihazı doğrulanmadan storage şeması tasarlamak erken bir
güvenlik kararı olur). Bu yüzden bu modül şimdilik yalnızca **tek bir**,
kullanıcı tarafından `.env` üzerinden açıkça verilen hedefi çözer — yani
"bana IP/VERSION/PORT/CREDENTIAL REF ver, ben sadece onu kullanayım"
akışının env-tabanlı karşılığı. `SNMP_TARGET_VERSION` hem `v2c` hem `v3`
olabilir (Faz 22.4). Eşleşme yoksa (varsayılan durum) `None` döner ve
`POST /api/snmp/poll/{asset_id}` mevcut `not_configured` davranışını
korur.

Faz 29.5: kalıcı çoklu-asset profil yönetimi artık VAR
(`asset_snmp_profiles` tablosu, bkz. `app/db/asset_snmp_profiles.py`).
`resolve_profile_for_asset(conn, asset)` bunun gerçek entegrasyon
noktasıdır — önce DB'deki asset↔profile atamasını dener, yalnızca hiç
atama yoksa (ya da `conn` hiç verilmemişse — ör. `conn`sız çağıran testler)
aşağıdaki `get_profile_for_asset()` `.env` tek-hedef fallback'ine düşer.
`.env` fallback'i bilinçli olarak KALDIRILMADI — dokümante edilmiş bir
geriye dönük uyumluluk yolu olarak korunuyor (bkz. `docs/decisions.md`)."""

import os
from uuid import UUID

from app.db import asset_snmp_profiles as asset_profiles_repo
from app.snmp.credentials import SNMPAuthProtocol, SNMPPrivProtocol, SNMPProfile
from app.snmp.profile_config import row_to_domain_profile


async def resolve_profile_for_asset(conn, asset: dict) -> SNMPProfile | None:
    """Yeni tercih edilen entegrasyon noktası (Faz 29.5).

    Akış: `asset_snmp_profiles` üzerinden bu asset'e atanmış bir profil
    var mı bak -> varsa ve `enabled=True` ise `snmp_profiles` satırından
    bir `SNMPProfile` kur (correlation_id = gerçek asset id, poll her
    zaman `asset["ip_address"]`'e gider — `profile.target_host` asset'e
    bağlı poll'da HİÇ okunmaz, yalnızca profilin kendi "Test Connection"
    akışında kullanılır). Atama `enabled=False` ise (kullanıcının bilinçli
    devre dışı bırakma tercihi) `.env` fallback'ine DÜŞÜLMEZ, doğrudan
    `None` (-> `not_configured`) döner. Hiç atama yoksa (veya `conn`
    verilmemişse) geriye dönük uyumluluk için `.env` tabanlı tek-hedef
    `get_profile_for_asset()`'e düşülür."""
    if conn is not None:
        row = await asset_profiles_repo.get_profile_for_asset(conn, asset["id"])
        if row is not None:
            if not row["enabled"]:
                return None
            return row_to_domain_profile(row, asset["id"])
    return get_profile_for_asset(asset["id"])


def get_profile_for_asset(asset_id: UUID) -> SNMPProfile | None:
    """`SNMP_TARGET_ASSET_ID` ortam değişkeni bu asset'in id'siyle
    eşleşiyorsa geri kalan `SNMP_TARGET_*` değişkenlerinden bir
    `SNMPProfile` kurar. Hiçbir gerçek secret DEĞERİ burada okunmaz —
    yalnızca `*_ref` (birer isim) taşınır; gerçek değer
    `secrets.resolve_secret()` ile, yalnızca poll anında okunur."""
    target_asset_id = os.environ.get("SNMP_TARGET_ASSET_ID")
    if not target_asset_id or target_asset_id.strip().lower() != str(asset_id).lower():
        return None

    common = _read_common_fields()
    if common is None:
        return None
    port, timeout_seconds, retries = common

    version = os.environ.get("SNMP_TARGET_VERSION", "v2c")
    if version == "v2c":
        return _v2c_profile(asset_id, port, timeout_seconds, retries)
    if version == "v3":
        return _v3_profile(asset_id, port, timeout_seconds, retries)
    return None


def _read_common_fields() -> tuple[int, float, int] | None:
    port_raw = os.environ.get("SNMP_TARGET_PORT", "161")
    timeout_raw = os.environ.get("SNMP_TARGET_TIMEOUT_SECONDS", "2.0")
    retries_raw = os.environ.get("SNMP_TARGET_RETRIES", "1")
    try:
        return int(port_raw), float(timeout_raw), int(retries_raw)
    except ValueError:
        return None


def _v2c_profile(asset_id: UUID, port: int, timeout_seconds: float, retries: int) -> SNMPProfile | None:
    community_ref = os.environ.get("SNMP_TARGET_COMMUNITY_REF")
    if not community_ref:
        return None
    try:
        return SNMPProfile(
            asset_id=asset_id,
            version="v2c",
            port=port,
            timeout_seconds=timeout_seconds,
            retries=retries,
            community_ref=community_ref,
        )
    except ValueError:
        return None


def _v3_profile(asset_id: UUID, port: int, timeout_seconds: float, retries: int) -> SNMPProfile | None:
    username = os.environ.get("SNMP_TARGET_USERNAME")
    if not username:
        return None

    auth_protocol_raw = os.environ.get("SNMP_TARGET_AUTH_PROTOCOL")
    auth_credential_ref = os.environ.get("SNMP_TARGET_AUTH_CREDENTIAL_REF")
    priv_protocol_raw = os.environ.get("SNMP_TARGET_PRIV_PROTOCOL")
    priv_credential_ref = os.environ.get("SNMP_TARGET_PRIV_CREDENTIAL_REF")

    auth_protocol: SNMPAuthProtocol | None = auth_protocol_raw or None  # type: ignore[assignment]
    priv_protocol: SNMPPrivProtocol | None = priv_protocol_raw or None  # type: ignore[assignment]

    try:
        return SNMPProfile(
            asset_id=asset_id,
            version="v3",
            port=port,
            timeout_seconds=timeout_seconds,
            retries=retries,
            username=username,
            auth_protocol=auth_protocol,
            auth_credential_ref=auth_credential_ref,
            priv_protocol=priv_protocol,
            priv_credential_ref=priv_credential_ref,
        )
    except ValueError:
        # Örn. yalnızca priv verilip auth verilmemiş — geçersiz bir
        # yapılandırma, sessizce None dönüp not_configured'a düşülür
        # (SNMPProfile'ın kendi model_validator'ı zaten reddetti).
        return None
