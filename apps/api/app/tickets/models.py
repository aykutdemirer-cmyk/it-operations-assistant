"""Faz 62 — IT Helpdesk / Arıza Yönetimi (Ticket Management) veri
modelleri. PAM'den TAMAMEN bağımsız; `created_by`/`assigned_to`
yalnızca `users`'a (Faz 46 auth) bağlıdır."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

TicketPriority = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
TicketStatus = Literal["OPEN", "IN_PROGRESS", "WAITING_USER", "RESOLVED", "CLOSED"]

# Oluşturma anında `sla_due_at = created_at + <öncelik süresi>` olarak
# hesaplanır (bkz. `service.py::_sla_hours_for_priority`). Sabit,
# hardcode değil — tek yerde.
SLA_HOURS_BY_PRIORITY: dict[str, int] = {
    "CRITICAL": 4,
    "HIGH": 24,
    "MEDIUM": 72,
    "LOW": 168,
}


class TicketCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20000)
    # Faz 63 — dinamik taksonomi: `category_id` ZORUNLU, `department_id`
    # opsiyonel. Faz 62'nin sabit `category` enum'ı + `related_device`
    # serbest metni KALDIRILDI.
    category_id: UUID
    department_id: UUID | None = None
    priority: TicketPriority = "MEDIUM"


class TicketTaxonomyCreateRequest(BaseModel):
    """Faz 63 — Admin'in yeni departman/kategori eklemesi."""

    name: str = Field(min_length=1, max_length=200)


class TicketTaxonomyItem(BaseModel):
    id: UUID
    name: str
    is_active: bool


class TicketCommentCreateRequest(BaseModel):
    """Tek bir çağrıyla hem yorum yazma HEM durum/atama değişikliği
    yapılabilir (spec: "Yanıt yazma veya durum/atama güncelleme").
    Üçü de opsiyonel; hiçbiri verilmezse 422 (bkz. route)."""

    body: str | None = Field(default=None, max_length=20000)
    status: TicketStatus | None = None
    # `assigned_to`: yeni atanan kullanıcı id'si. Açıkça `null` gönderilirse
    # atama KALDIRILIR; alan hiç gönderilmezse atama DEĞİŞMEZ — bu ayrım
    # route katmanında `model_fields_set` ile korunur.
    assigned_to: UUID | None = None
    # Yalnızca IT ekibi (TECHNICIAN/ADMIN) `body` ile birlikte true
    # gönderebilir — REQUESTER'dan gelirse servis katmanında sessizce
    # False'a zorlanır (bkz. `service.py::add_comment`).
    is_internal: bool = False


class TicketCommentResponse(BaseModel):
    id: UUID
    ticket_id: UUID
    author_id: UUID
    author_username: str
    event: Literal["created", "comment", "status_change", "assignment"]
    body: str | None
    status_from: TicketStatus | None
    status_to: TicketStatus | None
    assigned_from_username: str | None
    assigned_to_username: str | None
    is_internal: bool
    created_at: datetime


class TicketResponse(BaseModel):
    id: UUID
    ticket_number: str
    title: str
    description: str
    # Faz 63 — dinamik taksonomi (id + gösterim adı birlikte).
    category_id: UUID | None
    category_name: str | None
    department_id: UUID | None
    department_name: str | None
    priority: TicketPriority
    status: TicketStatus
    created_by: UUID
    created_by_username: str
    assigned_to: UUID | None
    assigned_to_username: str | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    sla_due_at: datetime | None
    # Yalnızca `GET /api/tickets/{id}` dönüşünde dolu; liste yanıtında boş.
    comments: list[TicketCommentResponse] = Field(default_factory=list)


class TicketStats(BaseModel):
    open_tickets: int
    assigned_to_me: int
    critical_or_overdue: int
    resolved_this_month: int


class TicketListResponse(BaseModel):
    tickets: list[TicketResponse]
    total: int
    stats: TicketStats


class TicketDailyPoint(BaseModel):
    day: str
    created: int
    resolved: int


class TicketMetricsResponse(BaseModel):
    """Faz 68 — salt-okunur helpdesk metrikleri."""

    total: int
    open_tickets: int
    closed_tickets: int
    overdue_open: int
    avg_resolution_hours: float | None
    sla_compliance_pct: float | None
    by_status: dict[str, int]
    by_priority: dict[str, int]
    by_category: dict[str, int]
    by_department: dict[str, int]
    daily: list[TicketDailyPoint]
