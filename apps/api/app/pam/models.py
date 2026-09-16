"""Faz 46 — PAM veri modelleri. `VaultCredentialResponse` HİÇBİR ZAMAN
gerçek parola/anahtar değeri taşımaz (`secret_masked` sabit `"••••••••"`)
— gerçek değer yalnızca `VaultCredentialRevealResponse` ile, ayrı,
Admin-only bir endpoint'ten (`GET .../reveal`) döner."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

CredentialType = Literal["password", "ssh_key"]
# Faz 76 — 'web' yalnızca `pam_session_logs.protocol`de geçerli (PAM
# Web Konsolu); `PamAccessRuleCreateRequest`/`AccessRequestResponse`nin
# TEK protokol seçen alanları (`pam_access_requests.protocol`) hâlâ
# yalnızca ssh/rdp kabul ediyor (bkz. docs/roadmap.md Faz 76 kapsam
# dışı) — bu yüzden AYRI bir tip.
Protocol = Literal["ssh", "rdp"]
SessionProtocol = Literal["ssh", "rdp", "web"]

_MASK = "••••••••"


class VaultCredentialCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    credential_type: CredentialType
    username: str = Field(min_length=1, max_length=200)
    domain: str | None = None
    # Şifrelenip DB'ye yalnızca `encrypted_payload` olarak yazılır —
    # bu istek modeli dışındaki hiçbir response'ta tekrar görünmez.
    password: str | None = None
    private_key: str | None = None
    passphrase: str | None = None


class VaultCredentialUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    username: str | None = Field(default=None, min_length=1, max_length=200)
    domain: str | None = None
    password: str | None = None
    private_key: str | None = None
    passphrase: str | None = None


class VaultCredentialResponse(BaseModel):
    id: UUID
    name: str
    credential_type: CredentialType
    username: str
    domain: str | None
    secret_masked: str = _MASK
    created_at: datetime
    updated_at: datetime


class VaultCredentialRevealResponse(BaseModel):
    """Yalnızca `require_role("ADMIN")` arkasında döner. `password` VEYA
    `private_key`/`passphrase` dolu — `credential_type`'a göre diğeri
    her zaman `None`."""

    id: UUID
    credential_type: CredentialType
    password: str | None
    private_key: str | None
    passphrase: str | None


class PamAccessRuleCreateRequest(BaseModel):
    """Faz 49 — bir kural artık YEREL bir kullanıcıyı (`user_id`) VEYA
    bir AD grubunu (`ad_group_id`) hedefleyebilir — TAM OLARAK biri
    dolu olmalı (bkz. `infra/postgres/init.sql::pam_access_rules_user_
    xor_group` CHECK constraint'i ile AYNI kural, burada da erken
    doğrulanır).

    Faz 55 — cihaz hedefi de artık TEK bir `asset_id` YERİNE bir
    `tag_id` (etiket) veya `server_group_id` (statik cihaz grubu)
    olabilir — üçünden TAM OLARAK biri dolu olmalı (`pam_access_rules_
    device_target_xor` CHECK constraint'iyle AYNI kural)."""

    user_id: UUID | None = None
    ad_group_id: UUID | None = None
    asset_id: UUID | None = None
    tag_id: UUID | None = None
    server_group_id: UUID | None = None
    credential_id: UUID
    allow_rdp: bool = False
    allow_ssh: bool = False
    # Faz 76 — PAM Web Konsolu (zero-knowledge HTTPS kimlik enjeksiyonu).
    allow_web: bool = False
    max_session_duration_mins: int = Field(default=60, gt=0)
    valid_until: datetime | None = None

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "PamAccessRuleCreateRequest":
        if (self.user_id is None) == (self.ad_group_id is None):
            raise ValueError("Tam olarak bir tanesi dolu olmalı: user_id VEYA ad_group_id")
        device_targets = [self.asset_id, self.tag_id, self.server_group_id]
        if sum(1 for v in device_targets if v is not None) != 1:
            raise ValueError("Tam olarak bir tanesi dolu olmalı: asset_id VEYA tag_id VEYA server_group_id")
        return self


class PamAccessRuleUpdateRequest(BaseModel):
    credential_id: UUID | None = None
    allow_rdp: bool | None = None
    allow_ssh: bool | None = None
    allow_web: bool | None = None
    # Faz 54 — kuralı SİLMEDEN geçici olarak devre dışı bırakma anahtarı.
    is_active: bool | None = None
    max_session_duration_mins: int | None = Field(default=None, gt=0)
    # `None` gönderilip GÖNDERİLMEDİĞİ `model_fields_set` ile ayırt
    # edilir (bkz. app/pam/service.py) — "süresiz yap" (`None`, alan
    # set edilmiş) ile "bu alanı hiç değiştirme" (alan set edilmemiş)
    # farklı anlamlara gelir.
    valid_until: datetime | None = None


class PamAccessRuleResponse(BaseModel):
    id: UUID
    # Faz 49 — TAM OLARAK biri dolu: `user_id`+`username` (yerel kural)
    # VEYA `ad_group_id`+`ad_group_name` (AD grup kuralı).
    user_id: UUID | None
    username: str | None
    ad_group_id: UUID | None
    ad_group_name: str | None
    # Faz 55 — TAM OLARAK biri dolu: `asset_id`+hostname/IP (tek cihaz),
    # `tag_id`+`tag_name` (etiket), VEYA `server_group_id`+`server_
    # group_name` (statik cihaz grubu).
    asset_id: UUID | None
    asset_hostname: str | None
    asset_ip_address: str | None
    tag_id: UUID | None
    tag_name: str | None
    server_group_id: UUID | None
    server_group_name: str | None
    credential_id: UUID
    credential_name: str
    allow_rdp: bool
    allow_ssh: bool
    allow_web: bool
    is_active: bool
    max_session_duration_mins: int
    valid_until: datetime | None
    created_at: datetime
    updated_at: datetime


# ---- Faz 55 — cihaz etiketleri (tags) + statik cihaz grupları -------------


class TagCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class TagResponse(BaseModel):
    id: UUID
    name: str
    created_at: datetime


class TagAssetSummary(BaseModel):
    id: UUID
    hostname: str | None
    ip_address: str | None


class ServerGroupCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None


class ServerGroupUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None


class ServerGroupResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class ServerGroupAssetSummary(BaseModel):
    id: UUID
    hostname: str | None
    ip_address: str | None


class AuthorizedAssetResponse(BaseModel):
    """OPERATOR/VIEWER'ın KENDİSİNE atanmış olarak gördüğü liste —
    `GET /api/pam/my-access`. `credential_id` KASITLI olarak yok;
    kullanıcı hangi kasa hesabının kullanılacağını hiç bilmez/görmez."""

    asset_id: UUID
    asset_hostname: str | None
    asset_ip_address: str | None
    allow_rdp: bool
    allow_ssh: bool
    allow_web: bool
    max_session_duration_mins: int
    valid_until: datetime | None
    # Faz 58 — "PAM Launchpad" yükseltmesi: `assets.status` (Faz 0-9'un
    # GERÇEK discovery/SNMP verisi, yeni bir canlı probe TETİKLENMEZ)
    # ile `pam_session_logs`/`session_registry` çapraz kontrolünden
    # (Faz 51) türetilir — ikisi de UYDURULMAZ.
    is_online: bool
    active_sessions_count: int


class PamSessionLogResponse(BaseModel):
    id: UUID
    user_id: UUID
    username: str
    asset_id: UUID
    asset_hostname: str | None
    asset_ip_address: str | None
    credential_id: UUID | None
    credential_name: str | None
    protocol: SessionProtocol
    started_at: datetime
    ended_at: datetime | None
    # 'user_closed' | 'timeout' | 'error' | 'terminated_by_admin' (Faz 50)
    end_reason: str | None
    client_ip: str | None
    # Faz 50 — RDP: guacd `.guac` kayıt dosyasının yolu (bkz. app/pam/
    # guacd.py). `None` — kayıt hiç etkinleştirilmemiş (bkz. `GUACD_
    # RECORDING_PATH`) VEYA oturum SSH (SSH oturumları video KAYDETMEZ,
    # denetim izi `pam_keystrokes`'tir).
    recording_file_path: str | None
    terminated_by: UUID | None

    @property
    def is_active(self) -> bool:
        return self.ended_at is None


class PamKeystrokeResponse(BaseModel):
    """Faz 50 — `GET /api/pam/audit/{session_id}/keystrokes`. Yalnızca
    SSH oturumları için satır üretir (bkz. `app/agents/ssh_proxy.py::
    run_pam_ssh_websocket_session`'ın `on_keystroke` kancası)."""

    id: UUID
    recorded_at: datetime
    data: str


# ---- Faz 56 — Erişim Talepleri (Access Requests) --------------------------

AccessRequestStatus = Literal["pending", "approved", "rejected"]


class AccessRequestCreateRequest(BaseModel):
    """Faz 55'in cihaz-hedefi XOR'uyla AYNI desen — `asset_id`/`tag_id`/
    `server_group_id`'den TAM OLARAK biri dolu olmalı. Kimlik bilgisi
    (`credential_id`) BURADA YOK — talep eden kullanıcı hiçbir zaman
    hangi kasa hesabının kullanılacağını seçmez/görmez (Faz 46'nın
    "zero-knowledge" ilkesiyle tutarlı, onaylayan Admin seçer)."""

    asset_id: UUID | None = None
    tag_id: UUID | None = None
    server_group_id: UUID | None = None
    protocol: Protocol
    business_reason: str = Field(min_length=1, max_length=2000)
    requested_duration_mins: int = Field(default=60, gt=0)

    @model_validator(mode="after")
    def _exactly_one_device_target(self) -> "AccessRequestCreateRequest":
        targets = [self.asset_id, self.tag_id, self.server_group_id]
        if sum(1 for v in targets if v is not None) != 1:
            raise ValueError("Tam olarak bir tanesi dolu olmalı: asset_id VEYA tag_id VEYA server_group_id")
        return self


class AccessRequestApproveRequest(BaseModel):
    credential_id: UUID
    review_note: str | None = None


class AccessRequestRejectRequest(BaseModel):
    review_note: str | None = None


class AccessRequestResponse(BaseModel):
    id: UUID
    requester_id: UUID
    requester_username: str
    asset_id: UUID | None
    asset_hostname: str | None
    asset_ip_address: str | None
    tag_id: UUID | None
    tag_name: str | None
    server_group_id: UUID | None
    server_group_name: str | None
    protocol: Protocol
    business_reason: str
    requested_duration_mins: int
    status: AccessRequestStatus
    reviewed_by: UUID | None
    reviewed_by_username: str | None
    reviewed_at: datetime | None
    review_note: str | None
    created_at: datetime


# ---- Faz 76 — PAM Web Konsolu (zero-knowledge HTTPS kimlik enjeksiyonu) ---


class WebConsoleProfileRequest(BaseModel):
    port: int = Field(default=443, gt=0, le=65535)
    verify_ssl: bool = False
    login_path: str = Field(default="/login", min_length=1)
    username_field: str = Field(default="username", min_length=1)
    password_field: str = Field(default="password", min_length=1)


class WebConsoleProfileResponse(BaseModel):
    asset_id: UUID
    port: int
    verify_ssl: bool
    login_path: str
    username_field: str
    password_field: str
    updated_at: datetime


class WebConsoleSessionResponse(BaseModel):
    session_id: UUID
    proxy_url: str
    max_session_duration_mins: int
