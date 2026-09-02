"""SNMP credential/profile modeli — Faz 7 (mimari tasarım, henüz
persistence yok).

**Bu dosya hiçbir gerçek secret değeri taşımaz veya saklamaz.** `SNMPProfile`
yalnızca *yapılandırma* bilgisini (versiyon, port, timeout, hangi
credential'ın kullanılacağına dair bir REFERANS) modeller. Gerçek
community string / auth-priv parolaları:

- asla bu modelin bir alanı olarak (plaintext) tutulmaz,
- asla API response'una, log'a veya frontend'e serialize edilmez,
- asla veritabanına yazılmaz (henüz bir `snmp_profiles` tablosu YOK —
  bkz. `docs/decisions.md`, bu bilinçli bir karardır: gerçek bir SNMP
  ajanı/cihazı devreye girmeden credential storage şeması tasarlamak
  erken bir güvenlik kararı olur).

`credential_ref`/`auth_credential_ref`/`priv_credential_ref` alanları
yalnızca birer *isim* taşır (örn. bir `.env` değişken adı) — gerçek
değer, ayrı bir mekanizma (backend `.env`) tarafından, yalnızca poll
anında, bellekte okunur ve asla bu modelin bir örneğinde saklanmaz."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, model_validator

from app.snmp.models import SNMPVersion

# SHA-1 + tam SHA-2 ailesi (pysnmp 7.1.29'da doğrulandı — bkz.
# `client.py::_AUTH_PROTOCOL_MAP`, `docs/decisions.md` §10.2). MD5 yalnızca
# eski ajanlarla geriye dönük uyumluluk için tutuluyor; hiçbir yerde
# varsayılan (default) değildir — her zaman açıkça seçilmesi gerekir.
SNMPAuthProtocol = Literal["MD5", "SHA", "SHA224", "SHA256", "SHA384", "SHA512"]

# AES (128/192/256-bit) birincil tercih. DES yalnızca eski ajan
# uyumluluğu için tutuluyor; koddaki hiçbir yerde varsayılan değildir —
# `auth_protocol` gibi her zaman açıkça seçilmesi zorunludur.
SNMPPrivProtocol = Literal["DES", "AES", "AES192", "AES256"]

SNMPSecurityLevel = Literal["noAuthNoPriv", "authNoPriv", "authPriv"]


def validate_snmp_version_fields(
    *,
    version: str,
    community_ref: str | None,
    username: str | None,
    auth_protocol: str | None,
    auth_credential_ref: str | None,
    priv_protocol: str | None,
    priv_credential_ref: str | None,
) -> None:
    """`SNMPProfile` ve `app/snmp/profile_config.py`'nin CRUD
    modellerinin PAYLAŞTIĞI v2c/v3 alan doğrulaması — iki yerde
    tekrarlanmasın diye buraya çıkarıldı (Faz 29). `ValueError`
    fırlatır, çağıran taraf (pydantic `model_validator`) bunu kendi
    `ValidationError`'ına çevirir."""
    if version == "v2c":
        if not community_ref:
            raise ValueError("v2c profili için community_ref zorunludur")
    elif version == "v3":
        if not username:
            raise ValueError("v3 profili için username zorunludur")
        if bool(auth_protocol) != bool(auth_credential_ref):
            raise ValueError(
                "auth_protocol belirtildiyse auth_credential_ref de (ve tersi) zorunludur"
            )
        if priv_protocol or priv_credential_ref:
            if not auth_protocol:
                raise ValueError(
                    "priv_protocol/priv_credential_ref için önce auth_protocol + "
                    "auth_credential_ref zorunludur"
                )
            if bool(priv_protocol) != bool(priv_credential_ref):
                raise ValueError(
                    "priv_protocol belirtildiyse priv_credential_ref de (ve tersi) zorunludur"
                )


def derive_security_level(
    version: str, auth_protocol: str | None, priv_protocol: str | None
) -> SNMPSecurityLevel | None:
    """`SNMPProfile.security_level` ve profil CRUD response'unun
    PAYLAŞTIĞI türetme mantığı."""
    if version != "v3":
        return None
    if priv_protocol:
        return "authPriv"
    if auth_protocol:
        return "authNoPriv"
    return "noAuthNoPriv"


class SNMPProfile(BaseModel):
    """Bir asset için SNMP polling yapılandırması.

    v2c: yalnızca `community_ref` gerekir.

    v3: `username` her zaman zorunlu; güvenlik seviyesi hangi alanların
    dolu olduğuna göre kendiliğinden belirlenir (bkz. `security_level`):
    - yalnızca `username` → `noAuthNoPriv`.
    - `+ auth_protocol + auth_credential_ref` → `authNoPriv`.
    - `+ priv_protocol + priv_credential_ref` → `authPriv` (privacy,
      authentication olmadan asla kullanılamaz — SNMPv3/USM'in kendi
      kuralı, bkz. RFC 3414)."""

    asset_id: UUID
    version: SNMPVersion
    port: int = 161
    timeout_seconds: float = 2.0
    retries: int = 1

    # v2c
    community_ref: str | None = None

    # v3
    username: str | None = None
    auth_protocol: SNMPAuthProtocol | None = None
    auth_credential_ref: str | None = None
    priv_protocol: SNMPPrivProtocol | None = None
    priv_credential_ref: str | None = None

    @model_validator(mode="after")
    def _validate_version_fields(self) -> "SNMPProfile":
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

    @property
    def security_level(self) -> SNMPSecurityLevel | None:
        """v3 için gerçek güvenlik seviyesi; v2c için `None`."""
        return derive_security_level(self.version, self.auth_protocol, self.priv_protocol)
