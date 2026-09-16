"""Faz 49 — LDAP/AD yapılandırma ve senkronizasyon Pydantic modelleri."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

_MASK = "••••••••"


class LdapConfigRequest(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=389, gt=0, le=65535)
    use_ssl: bool = False
    domain_fqdn: str = Field(min_length=1, max_length=255)
    base_dn: str = Field(min_length=1, max_length=500)
    bind_dn: str = Field(min_length=1, max_length=500)
    # Yalnızca bu istek modelinde — DB'ye YALNIZCA şifreli hali yazılır
    # (bkz. app/services/ldap.py::encrypt_bind_password), hiçbir
    # response'ta düz metin olarak geri dönmez. `None`/boş — Vault
    # kimlik bilgisi güncellemesiyle (`VaultCredentialUpdateRequest`)
    # AYNI ilke — "bu alanı DEĞİŞTİRME" anlamına gelir; route katmanı
    # (ilk kayıtta zorunlu, güncellemede mevcut şifreli değeri korur)
    # bu ayrımı çözer.
    bind_password: str | None = Field(default=None, min_length=1)


class LdapConfigResponse(BaseModel):
    host: str
    port: int
    use_ssl: bool
    domain_fqdn: str
    base_dn: str
    bind_dn: str
    bind_password_masked: str = _MASK
    last_sync_status: str | None
    last_sync_error: str | None
    last_sync_at: datetime | None
    updated_at: datetime


class LdapTestResult(BaseModel):
    success: bool
    message: str


class LdapSyncResult(BaseModel):
    groups_synced: int
    users_synced: int
    memberships_synced: int


class AdGroupResponse(BaseModel):
    id: UUID
    distinguished_name: str
    name: str
    synced_at: datetime


class AdUserResponse(BaseModel):
    """Faz 52 — `/pam/users`'ın "Active Directory'den İçe Aktar"
    seçicisinin veri kaynağı."""

    id: UUID
    distinguished_name: str
    username: str
    display_name: str | None
    email: str | None
    synced_at: datetime
