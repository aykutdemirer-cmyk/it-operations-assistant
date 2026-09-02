"""SNMP Profile Configuration Center — Pydantic modelleri (Faz 29).

`app/snmp/credentials.py::SNMPProfile` (poll anında kullanılan domain
modeli, `asset_id` zorunlu) ile KARIŞTIRILMAMALI: bu modeller
kullanıcının Settings > SNMP Configuration Center üzerinden YÖNETTİĞİ
kalıcı, `target_host`-tabanlı (bir asset'e bağlı OLMAYAN) profil
kayıtlarını temsil eder — bkz. `docs/decisions.md` §10.3. İkisi
arasındaki v2c/v3 alan doğrulaması `credentials.py::
validate_snmp_version_fields`/`derive_security_level` ile PAYLAŞILIR,
tekrarlanmaz.

`SNMPProfileResponse` hiçbir zaman secret DEĞERİ taşımaz — yalnızca
`*_ref` (bir isim) alanları ve `credential_configured`/`status` gibi
TÜRETİLMİŞ, secret olmayan bilgiler."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, field_validator, model_validator

from app.snmp.credentials import (
    SNMPAuthProtocol,
    SNMPPrivProtocol,
    SNMPProfile,
    SNMPSecurityLevel,
    derive_security_level,
    validate_snmp_version_fields,
)
from app.snmp.models import SNMPVersion

SNMPProfileStatus = Literal["ready", "not_configured", "disabled"]


class SNMPProfileWriteRequest(BaseModel):
    """`POST`/`PUT /api/snmp/profiles` gövdesi — create/update aynı
    şekli paylaşır (PUT tam yerine geçer, PATCH değil)."""

    name: str
    target_host: str
    port: int = 161
    version: SNMPVersion
    timeout_seconds: float = 2.0
    retries: int = 1
    enabled: bool = True

    # v2c
    community_ref: str | None = None

    # v3
    username: str | None = None
    auth_protocol: SNMPAuthProtocol | None = None
    auth_credential_ref: str | None = None
    priv_protocol: SNMPPrivProtocol | None = None
    priv_credential_ref: str | None = None

    @field_validator("name", "target_host")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("boş olamaz")
        return value.strip()

    @field_validator("port")
    @classmethod
    def _valid_port(cls, value: int) -> int:
        if not (1 <= value <= 65535):
            raise ValueError("port 1-65535 aralığında olmalı")
        return value

    @field_validator("timeout_seconds")
    @classmethod
    def _valid_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeout_seconds pozitif olmalı")
        return value

    @field_validator("retries")
    @classmethod
    def _valid_retries(cls, value: int) -> int:
        if value < 0:
            raise ValueError("retries negatif olamaz")
        return value

    @model_validator(mode="after")
    def _validate_version_fields(self) -> "SNMPProfileWriteRequest":
        validate_snmp_version_fields(
            version=self.version,
            community_ref=self.community_ref,
            username=self.username,
            auth_protocol=self.auth_protocol,
            auth_credential_ref=self.auth_credential_ref,
            priv_protocol=self.priv_protocol,
            priv_credential_ref=self.priv_credential_ref,
        )
        return self


class SNMPProfileResponse(BaseModel):
    id: UUID
    name: str
    target_host: str
    port: int
    version: SNMPVersion
    timeout_seconds: float
    retries: int
    enabled: bool
    credential_configured: bool
    status: SNMPProfileStatus
    security_level: SNMPSecurityLevel | None
    # Faz 29.5 — bu profile atanmış (bkz. `asset_snmp_profiles`) asset
    # sayısı; Settings UI'daki "Assigned Devices" sütunu için.
    assigned_asset_count: int
    # Yalnızca REFERANS isimleri (env değişken adı) — gerçek secret
    # DEĞERİ hiçbir zaman burada yer almaz. Düzenleme formunun mevcut
    # referansı geri gösterebilmesi için gerekli.
    community_ref: str | None
    username: str | None
    auth_protocol: SNMPAuthProtocol | None
    auth_credential_ref: str | None
    priv_protocol: SNMPPrivProtocol | None
    priv_credential_ref: str | None
    created_at: datetime
    updated_at: datetime


def row_to_response(
    row: dict, *, secret_configured: bool, assigned_asset_count: int = 0
) -> SNMPProfileResponse:
    """DB satırını response modeline çevirir. `secret_configured`
    çağıran taraftan (bkz. `service.py`) gelir — bu fonksiyon secret
    DEĞERİNE hiç dokunmaz, yalnızca `resolve_secret()`'ın sonucunun
    bilgisini (var/yok) taşır."""
    enabled = row["enabled"]
    status: SNMPProfileStatus = "disabled" if not enabled else ("ready" if secret_configured else "not_configured")
    return SNMPProfileResponse(
        id=row["id"],
        name=row["name"],
        target_host=row["target_host"],
        port=row["port"],
        version=row["version"],
        timeout_seconds=row["timeout_seconds"],
        retries=row["retries"],
        enabled=enabled,
        credential_configured=secret_configured,
        status=status,
        security_level=derive_security_level(row["version"], row.get("auth_protocol"), row.get("priv_protocol")),
        assigned_asset_count=assigned_asset_count,
        community_ref=row.get("community_ref"),
        username=row.get("username"),
        auth_protocol=row.get("auth_protocol"),
        auth_credential_ref=row.get("auth_credential_ref"),
        priv_protocol=row.get("priv_protocol"),
        priv_credential_ref=row.get("priv_credential_ref"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def row_to_domain_profile(row: dict, correlation_id: UUID) -> SNMPProfile | None:
    """`snmp_profiles` DB satırını `SNMPClient.poll_asset`'in beklediği
    domain modeline çevirir (Faz 29.5) — hem profilin KENDİ "Test
    Connection"'ı (`profile_service.py`, `correlation_id` = profilin
    kendi id'si) hem de bir asset'e bağlı gerçek poll (`profile_store.py`,
    `correlation_id` = gerçek `asset.id`) tarafından PAYLAŞILIR.
    `SNMPProfile.asset_id` alanı yalnızca bir KORELASYON anahtarıdır
    (bant genişliği önbelleği + `SNMPPollResult.asset_id` için) —
    gerçek bir `assets.id` olmak ZORUNDA değildir (bkz. `client.py`).
    Satır DB'de zaten doğrulanmış olduğu için (`SNMPProfileWriteRequest`
    validator'ı) normalde `None` dönmez; yalnızca beklenmeyen bir veri
    bozulmasına karşı savunma amaçlı."""
    try:
        return SNMPProfile(
            asset_id=correlation_id,
            version=row["version"],
            port=row["port"],
            timeout_seconds=row["timeout_seconds"],
            retries=row["retries"],
            community_ref=row.get("community_ref"),
            username=row.get("username"),
            auth_protocol=row.get("auth_protocol"),
            auth_credential_ref=row.get("auth_credential_ref"),
            priv_protocol=row.get("priv_protocol"),
            priv_credential_ref=row.get("priv_credential_ref"),
        )
    except ValueError:
        return None
