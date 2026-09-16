"""Faz 46/47 — Auth/RBAC veri modelleri. Bu proje şimdiye kadar hiçbir
insan kullanıcı girişi olmadan çalışıyordu (bkz. docs/decisions.md
§17); bu modül PAM'in önkoşulu olan gerçek kullanıcı sisteminin
kendisidir.

`role` (ADMIN/OPERATOR/VIEWER) genel kademe/varsayılan izin ataması
için kullanılmaya devam ediyor, ama Faz 47'den itibaren gerçek
yetkilendirme kararları `permissions` (ince taneli, kişi bazında
override edilebilir izin listesi — bkz. `app/auth/permissions.py`)
üzerinden veriliyor."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.auth.permissions import Permission

UserRole = Literal["ADMIN", "OPERATOR", "VIEWER"]
# Faz 65 — bilet-modülüne özel rol ekseni (mevcut `role`'dan bağımsız).
TicketRole = Literal["REQUESTER", "TECHNICIAN", "ADMIN"]


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8, max_length=200)
    role: UserRole = "VIEWER"
    full_name: str | None = None
    ticket_role: TicketRole = "REQUESTER"


class UserCreateFromAdRequest(BaseModel):
    """Faz 52 — `/pam/users`'ın "Active Directory'den İçe Aktar" akışı.
    Admin'in ELLE tetiklediği bir provizyon — `authenticate_and_
    provision`'ın AKSİNE canlı bir LDAP bind GEREKMEZ, yalnızca `ad_
    username`'in ZATEN senkronize edilmiş `ad_users`'ta bulunması
    yeterli (bkz. app/services/ldap_auth.py::create_user_from_ad)."""

    ad_username: str = Field(min_length=1)
    role: UserRole = "VIEWER"


class UserUpdateRequest(BaseModel):
    """Tüm alanlar opsiyonel — yalnızca gönderilenler güncellenir. Parola
    boş/None geçilirse DEĞİŞTİRİLMEZ (ayrı bir "parola sıfırla" akışı
    değil, sade bir kısmi güncelleme)."""

    role: UserRole | None = None
    full_name: str | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=200)
    # Faz 49 — bu yerel hesabı bir AD hesabına (sAMAccountName) bağlar;
    # `None` gönderilip alan set edilirse bağlantı kaldırılır.
    ad_username: str | None = None
    # Faz 65 — bilet rolü (yalnızca gönderilirse güncellenir).
    ticket_role: TicketRole | None = None


class UserResponse(BaseModel):
    """`password_hash` bu modelde YOK — hiçbir API yanıtı parola
    hash'ini bile dışarı sızdırmaz. `permissions` her zaman DB'den TAZE
    okunur (JWT payload'ında SAKLANMAZ) — admin bir izni geri alınca
    kullanıcının halihazırda geçerli token'ı bir sonraki istekte bunu
    hemen yansıtır, token'ın süresi dolmasını beklemez."""

    id: UUID
    username: str
    role: UserRole
    full_name: str | None
    is_active: bool
    ad_username: str | None
    permissions: list[Permission]
    ticket_role: TicketRole = "REQUESTER"
    created_at: datetime
    updated_at: datetime


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in_seconds: int
    user: UserResponse


class PermissionsUpdateRequest(BaseModel):
    """`PUT /api/pam/users/{id}/permissions` — TAM yer değiştirme
    (ekleme değil); gönderilmeyen bir izin kaldırılmış sayılır. Admin
    panelindeki checkbox matrisiyle birebir eşleşir."""

    permissions: list[Permission]
