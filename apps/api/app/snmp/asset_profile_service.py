"""Asset ↔ SNMP Profile ilişki servisi (Faz 29.5).

Mimari karar: `SNMPProfile` bağlantı/credential YAPILANDIRMASINI temsil
eder; `Asset` gerçek cihazı temsil eder. İkisi arasındaki ilişki
`asset_snmp_profiles` tablosu üzerinden kurulur (bkz. `docs/decisions.md`
§10.5) — bir profil BİRDEN FAZLA asset'e atanabilir, ama her asset aynı
anda en fazla BİR aktif profile sahip olabilir.

**Güvenlik/doğruluk garantisi:** Gerçek SNMP poll'unun hedefi HER ZAMAN
`asset.ip_address`'tir — `snmp_profiles.target_host` bir asset'e bağlı
poll'da HİÇ okunmaz (yalnızca profilin kendi bağımsız "Test Connection"ı
için kullanılır, bkz. `profile_service.py::test_connection`). Bu,
yapısal olarak "başka bir cihaza yanlışlıkla SNMP isteği gönderme"
riskini ortadan kaldırır — `target_host` alanı asset-bağlı poll
akışında zaten hiç dikkate alınmaz."""

from uuid import UUID

import asyncpg
from pydantic import BaseModel

from app.db import asset_snmp_profiles as asset_profiles_repo
from app.db import assets as assets_repo
from app.db import snmp_profiles as profiles_repo
from app.snmp.profile_config import SNMPProfileResponse, row_to_response
from app.snmp.profile_service import SNMPProfileNotFoundError, is_credential_configured


class AssetNotFoundError(Exception):
    """Verilen `asset_id` ile eşleşen bir asset yok."""


class AssetSnmpProfileResponse(BaseModel):
    configured: bool
    profile: SNMPProfileResponse | None
    # Bilgilendirme amaçlı — profilin kendi `target_host`'u bu asset'in
    # gerçek IP'sinden farklıysa `False`. Poll DAVRANIŞINI etkilemez
    # (poll her zaman `asset.ip_address`'i kullanır) — yalnızca UI'nin
    # kullanıcıyı bilgilendirmesi için (bkz. modül docstring'i).
    target_host_matches_asset: bool | None = None


class AssetSummary(BaseModel):
    """`GET /api/snmp/profiles/{id}/assets` liste öğesi — tam `Asset`
    şeması değil, yalnızca bir profile atanmış cihazları tanımaya yeten
    alanlar."""

    id: UUID
    ip_address: str
    hostname: str | None
    device_type: str
    status: str


def _profile_row_to_response(row: dict) -> SNMPProfileResponse:
    # `row` burada `asset_snmp_profiles JOIN snmp_profiles` sonucu —
    # `assigned_asset_count` bu görünümde anlamlı değil (tek bir asset'e
    # atanmış profili gösteriyoruz, "kaç asset'e atanmış" ayrı bir soru)
    # — 0 ile dolduruluyor, ihtiyaç olursa ayrı sorgulanabilir.
    return row_to_response(row, secret_configured=is_credential_configured(row))


async def get_profile_for_asset(conn: asyncpg.Connection, asset_id: UUID) -> AssetSnmpProfileResponse:
    asset = await assets_repo.get_asset_by_id(conn, asset_id)
    if asset is None:
        raise AssetNotFoundError(f"Asset bulunamadı: {asset_id}")

    row = await asset_profiles_repo.get_profile_for_asset(conn, asset_id)
    if row is None:
        return AssetSnmpProfileResponse(configured=False, profile=None)

    target_host_matches = (
        None if not row["target_host"] else row["target_host"] == str(asset["ip_address"])
    )
    return AssetSnmpProfileResponse(
        configured=True,
        profile=_profile_row_to_response(row),
        target_host_matches_asset=target_host_matches,
    )


async def list_assets_for_profile(conn: asyncpg.Connection, profile_id: UUID) -> list[AssetSummary]:
    profile_row = await profiles_repo.get_profile_by_id(conn, profile_id)
    if profile_row is None:
        raise SNMPProfileNotFoundError(f"Profil bulunamadı: {profile_id}")

    rows = await asset_profiles_repo.list_assets_for_profile(conn, profile_id)
    return [
        AssetSummary(
            id=row["id"],
            ip_address=str(row["ip_address"]),
            hostname=row.get("hostname"),
            device_type=row["device_type"],
            status=row["status"],
        )
        for row in rows
    ]


async def assign_profile_to_asset(
    conn: asyncpg.Connection, asset_id: UUID, profile_id: UUID
) -> None:
    """Var olan bir atamayı SESSİZCE ÜZERİNE YAZAR (reassign) — bu,
    kullanıcının "farklı bir profil seç" akışının kendisidir, ayrı bir
    "reassign" endpoint'i yok."""
    asset = await assets_repo.get_asset_by_id(conn, asset_id)
    if asset is None:
        raise AssetNotFoundError(f"Asset bulunamadı: {asset_id}")

    profile = await profiles_repo.get_profile_by_id(conn, profile_id)
    if profile is None:
        raise SNMPProfileNotFoundError(f"Profil bulunamadı: {profile_id}")

    await asset_profiles_repo.assign_profile_to_asset(conn, asset_id=asset_id, profile_id=profile_id)


async def unassign_profile_from_asset(conn: asyncpg.Connection, asset_id: UUID) -> bool:
    asset = await assets_repo.get_asset_by_id(conn, asset_id)
    if asset is None:
        raise AssetNotFoundError(f"Asset bulunamadı: {asset_id}")
    return await asset_profiles_repo.unassign_profile_from_asset(conn, asset_id)
