"""Faz 62 — Helpdesk orkestrasyon katmanı: bilet numarası üretimi,
SLA hesabı, yorum + durum/atama geçişlerinin zaman çizelgesine
kaydı. Route katmanı yalnızca HTTP çevirisi yapar."""

import csv
import io
from datetime import datetime, timedelta, timezone
from uuid import UUID

import asyncpg

from app.auth.dependencies import CurrentUser
from app.db import tickets as db
from app.db.users import get_user_by_id
from app.services import email_service
from app.tickets.models import (
    SLA_HOURS_BY_PRIORITY,
    TicketCommentCreateRequest,
    TicketCommentResponse,
    TicketCreateRequest,
    TicketListResponse,
    TicketMetricsResponse,
    TicketResponse,
    TicketStats,
    TicketTaxonomyItem,
)

# Faz 63 — "department"/"category" → gerçek tablo adı. Çağıran katman
# yalnızca bu iki sabitten birini geçer, tablo adı kullanıcı girdisi
# DEĞİL (SQL injection yüzeyi yok).
_TAXONOMY_TABLE = {"department": "ticket_departments", "category": "ticket_categories"}


class TicketNotFoundError(Exception):
    """Verilen bilet id'si `tickets`'ta yok."""


class AssigneeNotFoundError(Exception):
    """`assigned_to` olarak verilen kullanıcı id'si `users`'ta yok."""


class EmptyCommentError(Exception):
    """`POST .../comments` çağrısında body/status/assigned_to'nun HİÇBİRİ verilmedi."""


class CategoryInvalidError(Exception):
    """`category_id` yok ya da pasif."""


class DepartmentInvalidError(Exception):
    """`department_id` yok ya da pasif."""


class TaxonomyNameExistsError(Exception):
    """Aynı adda AKTİF bir departman/kategori zaten var."""


class TaxonomyItemNotFoundError(Exception):
    """Verilen departman/kategori id'si yok."""


class TicketAccessDeniedError(Exception):
    """Faz 65 — REQUESTER kendisi DIŞINDA birinin açtığı bir bileti
    görmeye/yorum yazmaya çalıştı (API seviyesinde 403)."""


def _is_it_staff(actor: CurrentUser) -> bool:
    """Faz 65 — IT ekibi (TECHNICIAN/ADMIN bilet rolü) tüm şirket
    biletlerini görür; REQUESTER (varsayılan) yalnızca kendi açtığını."""
    return getattr(actor, "ticket_role", "REQUESTER") in ("TECHNICIAN", "ADMIN")


async def _sla_hours(conn: asyncpg.Connection, priority: str) -> int:
    """Faz 67 — DB politikası (`ticket_sla_policy`), yoksa kod sabiti."""
    policy = await db.get_sla_policy(conn)
    return policy.get(priority) or SLA_HOURS_BY_PRIORITY[priority]


def _sla_due_at(hours: int, created_at: datetime) -> datetime:
    return created_at + timedelta(hours=hours)


async def _notify_owner(conn: asyncpg.Connection, ticket_row: asyncpg.Record, kind: str, *, status: str | None = None) -> None:
    owner = await get_user_by_id(conn, ticket_row["created_by"])
    email = owner["email"] if owner is not None and "email" in owner else None
    if not email:
        return
    email_service.notify(
        kind,
        recipients=[email],
        number=ticket_row["ticket_number"],
        title=ticket_row["title"],
        creator=ticket_row["created_by_username"],
        status=status,
    )


def _comment_to_response(row: asyncpg.Record) -> TicketCommentResponse:
    return TicketCommentResponse(
        id=row["id"],
        ticket_id=row["ticket_id"],
        author_id=row["author_id"],
        author_username=row["author_username"],
        event=row["event"],
        body=row["body"],
        status_from=row["status_from"],
        status_to=row["status_to"],
        assigned_from_username=row["assigned_from_username"],
        assigned_to_username=row["assigned_to_username"],
        is_internal=row["is_internal"],
        created_at=row["created_at"],
    )


def _ticket_to_response(row: asyncpg.Record, comments: list[asyncpg.Record] | None = None) -> TicketResponse:
    return TicketResponse(
        id=row["id"],
        ticket_number=row["ticket_number"],
        title=row["title"],
        description=row["description"],
        category_id=row["category_id"],
        category_name=row["category_name"],
        department_id=row["department_id"],
        department_name=row["department_name"],
        priority=row["priority"],
        status=row["status"],
        created_by=row["created_by"],
        created_by_username=row["created_by_username"],
        assigned_to=row["assigned_to"],
        assigned_to_username=row["assigned_to_username"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        resolved_at=row["resolved_at"],
        sla_due_at=row["sla_due_at"],
        comments=[_comment_to_response(c) for c in (comments or [])],
    )


async def create_ticket(conn: asyncpg.Connection, payload: TicketCreateRequest, *, created_by: UUID) -> TicketResponse:
    # Faz 63 — kategori zorunlu ve AKTİF olmalı; departman opsiyonel ama
    # verildiyse AKTİF olmalı.
    category = await db.get_taxonomy(conn, _TAXONOMY_TABLE["category"], payload.category_id)
    if category is None or not category["is_active"]:
        raise CategoryInvalidError

    if payload.department_id is not None:
        department = await db.get_taxonomy(conn, _TAXONOMY_TABLE["department"], payload.department_id)
        if department is None or not department["is_active"]:
            raise DepartmentInvalidError
        department_id = payload.department_id
    else:
        # Faz 65 — departman seçilmezse tüm biletler varsayılan olarak
        # "IT" departmanına açılır (seed departman, `infra/postgres/
        # init.sql`). Seed silinmişse departmansız kalır (akış bozulmaz).
        it_dept = await db.get_taxonomy_by_name(conn, _TAXONOMY_TABLE["department"], "IT")
        department_id = it_dept["id"] if it_dept is not None and it_dept["is_active"] else None

    now = datetime.now(timezone.utc)
    sla_hours = await _sla_hours(conn, payload.priority)
    async with conn.transaction():
        number = await db.next_ticket_number(conn, year=now.year)
        row = await db.insert_ticket(
            conn,
            ticket_number=number,
            title=payload.title.strip(),
            description=payload.description,
            category_id=payload.category_id,
            department_id=department_id,
            priority=payload.priority,
            created_by=created_by,
            sla_due_at=_sla_due_at(sla_hours, now),
        )
        await db.insert_comment(
            conn,
            ticket_id=row["id"],
            author_id=created_by,
            event="created",
            body=None,
            status_from=None,
            status_to=row["status"],
            assigned_from=None,
            assigned_to=None,
        )
    fresh = await db.get_ticket(conn, row["id"])
    comments = await db.list_comments(conn, row["id"])
    # Faz 65/66 — yeni bilet IT grup adresine bildirilir (ateşle-unut).
    # `recipients=None` → adres `smtp_config`/`.env`'den çözülür.
    email_service.notify(
        "new_ticket",
        recipients=None,
        number=fresh["ticket_number"],
        title=fresh["title"],
        creator=fresh["created_by_username"],
    )
    return _ticket_to_response(fresh, comments)


async def list_tickets(
    conn: asyncpg.Connection,
    *,
    actor: CurrentUser,
    status: str | None,
    priority: str | None,
    category_id: UUID | None,
    department_id: UUID | None,
    search: str | None,
    overdue: bool,
    mine: bool,
    limit: int,
    offset: int,
) -> TicketListResponse:
    scope = None if _is_it_staff(actor) else actor.id
    rows, total = await db.list_tickets(
        conn,
        status=status,
        priority=priority,
        category_id=category_id,
        department_id=department_id,
        search=search,
        created_by_scope=scope,
        assignee_scope=actor.id if mine else None,
        overdue=overdue,
        limit=limit,
        offset=offset,
    )
    stats_row = await db.ticket_stats(conn, user_id=actor.id, created_by_scope=scope)
    return TicketListResponse(
        tickets=[_ticket_to_response(r) for r in rows],
        total=total,
        stats=TicketStats(
            open_tickets=stats_row["open_tickets"],
            assigned_to_me=stats_row["assigned_to_me"],
            critical_or_overdue=stats_row["critical_or_overdue"],
            resolved_this_month=stats_row["resolved_this_month"],
        ),
    )


async def export_tickets_csv(
    conn: asyncpg.Connection,
    *,
    actor: CurrentUser,
    status: str | None,
    priority: str | None,
    category_id: UUID | None,
    department_id: UUID | None,
    search: str | None,
    overdue: bool,
    mine: bool,
) -> str:
    """Faz 69 — filtrelenmiş bilet listesini CSV metnine çevirir. Aynı
    RBAC (`created_by_scope`) uygulanır; stdlib `csv` — yeni bağımlılık
    yok. Üst sınır 5000 satır."""
    scope = None if _is_it_staff(actor) else actor.id
    rows, _ = await db.list_tickets(
        conn,
        status=status,
        priority=priority,
        category_id=category_id,
        department_id=department_id,
        search=search,
        created_by_scope=scope,
        assignee_scope=actor.id if mine else None,
        overdue=overdue,
        limit=5000,
        offset=0,
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "ticket_number", "title", "priority", "status", "category", "department",
            "created_by", "assigned_to", "created_at", "sla_due_at", "resolved_at",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r["ticket_number"], r["title"], r["priority"], r["status"],
                r["category_name"] or "", r["department_name"] or "",
                r["created_by_username"], r["assigned_to_username"] or "",
                r["created_at"].isoformat() if r["created_at"] else "",
                r["sla_due_at"].isoformat() if r["sla_due_at"] else "",
                r["resolved_at"].isoformat() if r["resolved_at"] else "",
            ]
        )
    return buf.getvalue()


async def get_metrics(conn: asyncpg.Connection, *, actor: CurrentUser) -> TicketMetricsResponse:
    """Faz 68 — REQUESTER yalnızca kendi biletlerinin metriklerini görür."""
    scope = None if _is_it_staff(actor) else actor.id
    data = await db.ticket_metrics(conn, created_by_scope=scope)
    return TicketMetricsResponse(**data)


async def get_ticket_detail(conn: asyncpg.Connection, ticket_id: UUID, *, actor: CurrentUser) -> TicketResponse:
    row = await db.get_ticket(conn, ticket_id)
    if row is None:
        raise TicketNotFoundError
    is_staff = _is_it_staff(actor)
    if not is_staff and row["created_by"] != actor.id:
        raise TicketAccessDeniedError
    # REQUESTER'a IT'nin gizli iç notları HİÇ dönmez.
    comments = await db.list_comments(conn, ticket_id, include_internal=is_staff)
    return _ticket_to_response(row, comments)


async def add_comment(
    conn: asyncpg.Connection,
    ticket_id: UUID,
    payload: TicketCommentCreateRequest,
    *,
    actor: CurrentUser,
) -> TicketResponse:
    """Tek çağrıyla: yorum + durum + atama. Her değişiklik zaman
    çizelgesine ayrı bir `ticket_comments` satırı olarak yazılır."""
    author_id = actor.id
    current = await db.get_ticket(conn, ticket_id)
    if current is None:
        raise TicketNotFoundError
    is_staff = _is_it_staff(actor)
    if not is_staff and current["created_by"] != actor.id:
        raise TicketAccessDeniedError

    fields = payload.model_fields_set
    body = payload.body.strip() if payload.body and payload.body.strip() else None
    # REQUESTER asla gizli iç not yazamaz — istese bile sessizce görünür
    # yanıta düşürülür (frontend zaten bu sekmeyi göstermiyor, bu yalnızca
    # API seviyesinde bir savunma katmanı).
    is_internal = bool(payload.is_internal) and is_staff
    wants_status = payload.status is not None and payload.status != current["status"]
    wants_assignee = "assigned_to" in fields and payload.assigned_to != current["assigned_to"]

    if body is None and not (wants_status or wants_assignee):
        raise EmptyCommentError

    if wants_assignee and payload.assigned_to is not None:
        if await get_user_by_id(conn, payload.assigned_to) is None:
            raise AssigneeNotFoundError

    async with conn.transaction():
        if wants_status or wants_assignee:
            new_status = payload.status if wants_status else current["status"]
            mark_resolved = wants_status and new_status in ("RESOLVED", "CLOSED") and current["resolved_at"] is None
            clear_resolved = (
                wants_status and new_status not in ("RESOLVED", "CLOSED") and current["resolved_at"] is not None
            )
            await db.update_ticket_status_and_assignee(
                conn,
                ticket_id,
                status=payload.status if wants_status else None,
                set_assignee=wants_assignee,
                assigned_to=payload.assigned_to if wants_assignee else None,
                mark_resolved=mark_resolved,
                clear_resolved=clear_resolved,
            )

        if body is not None:
            await db.insert_comment(
                conn,
                ticket_id=ticket_id,
                author_id=author_id,
                event="comment",
                body=body,
                status_from=None,
                status_to=None,
                assigned_from=None,
                assigned_to=None,
                is_internal=is_internal,
            )
        if wants_status:
            await db.insert_comment(
                conn,
                ticket_id=ticket_id,
                author_id=author_id,
                event="status_change",
                body=None,
                status_from=current["status"],
                status_to=payload.status,
                assigned_from=None,
                assigned_to=None,
            )
        if wants_assignee:
            await db.insert_comment(
                conn,
                ticket_id=ticket_id,
                author_id=author_id,
                event="assignment",
                body=None,
                status_from=None,
                status_to=None,
                assigned_from=current["assigned_to"],
                assigned_to=payload.assigned_to,
            )

    # Faz 65 — bilet sahibine e-posta (ateşle-unut). Sahip kendi bileti
    # üzerinde işlem yaptıysa ona haber vermeye gerek yok; gizli iç
    # notlar REQUESTER'a HİÇBİR ZAMAN e-posta olarak da gitmez.
    fresh = await db.get_ticket(conn, ticket_id)
    if fresh is not None and fresh["created_by"] != actor.id:
        new_status = fresh["status"]
        if wants_status and new_status in ("RESOLVED", "CLOSED"):
            await _notify_owner(conn, fresh, "resolved", status=new_status)
        elif body is not None and not is_internal:
            await _notify_owner(conn, fresh, "new_reply")

    return await get_ticket_detail(conn, ticket_id, actor=actor)


# ---- Faz 63 — Departman + Kategori yönetimi (Admin) -----------------


def _taxonomy_item(row: asyncpg.Record) -> TicketTaxonomyItem:
    return TicketTaxonomyItem(id=row["id"], name=row["name"], is_active=row["is_active"])


async def list_taxonomy(conn: asyncpg.Connection, kind: str, *, include_inactive: bool = False) -> list[TicketTaxonomyItem]:
    rows = await db.list_taxonomy(conn, _TAXONOMY_TABLE[kind], include_inactive=include_inactive)
    return [_taxonomy_item(r) for r in rows]


async def create_taxonomy(conn: asyncpg.Connection, kind: str, name: str) -> TicketTaxonomyItem:
    """Yeni ekle; aynı ad PASİF bir satırda varsa onu YENİDEN
    AKTİFLEŞTİRİR (silinen bir departmanı geri getirmenin yolu), AKTİF
    bir satırda varsa `TaxonomyNameExistsError`."""
    table = _TAXONOMY_TABLE[kind]
    name = name.strip()
    existing = await db.get_taxonomy_by_name(conn, table, name)
    if existing is not None:
        if existing["is_active"]:
            raise TaxonomyNameExistsError
        row = await db.set_taxonomy_active(conn, table, existing["id"], is_active=True)
        return _taxonomy_item(row)
    return _taxonomy_item(await db.insert_taxonomy(conn, table, name))


async def deactivate_taxonomy(conn: asyncpg.Connection, kind: str, item_id: UUID) -> TicketTaxonomyItem:
    """"Silme" = soft-delete (`is_active = false`). Mevcut biletlerin FK
    referansı korunur; liste/oluşturma artık bu satırı sunmaz."""
    row = await db.set_taxonomy_active(conn, _TAXONOMY_TABLE[kind], item_id, is_active=False)
    if row is None:
        raise TaxonomyItemNotFoundError
    return _taxonomy_item(row)


# ---- Faz 67 — SLA politikası (Admin) -------------------------------

_PRIORITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


async def get_sla_policy(conn: asyncpg.Connection) -> dict[str, int]:
    """Her öncelik için geçerli SLA saati — DB satırı yoksa kod sabiti
    doldurur (yanıt HER ZAMAN 4 önceliği de içerir)."""
    stored = await db.get_sla_policy(conn)
    return {p: stored.get(p) or SLA_HOURS_BY_PRIORITY[p] for p in _PRIORITIES}


async def set_sla_policy(conn: asyncpg.Connection, priority: str, sla_hours: int) -> dict[str, int]:
    if priority not in _PRIORITIES:
        raise ValueError(f"geçersiz öncelik: {priority}")
    await db.upsert_sla_policy(conn, priority, sla_hours)
    return await get_sla_policy(conn)
