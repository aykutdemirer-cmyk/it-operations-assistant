"""Faz 62/63 — `/api/tickets` (IT Helpdesk / Arıza Yönetimi). `/api/v1`
KULLANILMADI — bu proje hiçbir zaman versiyonlu URL kullanmadı (bkz.
Faz 42/54/56/58/59/60/61/62). Bilet route'ları `TICKETS_VIEW` iznine
tabidir (Faz 47); atama/durum "izni olan herkes". Faz 63 — departman/
kategori LİSTELEME `TICKETS_VIEW`, EKLEME/SİLME yalnızca `ADMIN`."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from app.auth.dependencies import CurrentUser, require_permission, require_role
from app.db.tickets import get_connection
from app.db.users import list_users
from app.tickets.models import (
    TicketCommentCreateRequest,
    TicketCreateRequest,
    TicketListResponse,
    TicketMetricsResponse,
    TicketResponse,
    TicketTaxonomyCreateRequest,
    TicketTaxonomyItem,
)
from app.tickets.service import (
    AssigneeNotFoundError,
    CategoryInvalidError,
    DepartmentInvalidError,
    EmptyCommentError,
    TaxonomyItemNotFoundError,
    TaxonomyNameExistsError,
    TicketAccessDeniedError,
    TicketNotFoundError,
    add_comment,
    create_taxonomy,
    create_ticket,
    deactivate_taxonomy,
    export_tickets_csv,
    get_metrics,
    get_sla_policy,
    get_ticket_detail,
    list_taxonomy,
    list_tickets,
    set_sla_policy,
)

router = APIRouter(prefix="/api/tickets", tags=["tickets"], dependencies=[Depends(require_permission("TICKETS_VIEW"))])

logger = logging.getLogger(__name__)


class AssignableUser(BaseModel):
    id: UUID
    username: str


async def _connect():
    try:
        return await get_connection()
    except OSError as exc:
        logger.warning("PostgreSQL erişilemedi (tickets)")
        raise HTTPException(status_code=503, detail={"database": "unreachable"}) from exc


# ---- Bilet listeleme / oluşturma / detay / yorum -------------------


@router.get("", response_model=TicketListResponse)
async def list_tickets_route(
    status: str | None = None,
    priority: str | None = None,
    category_id: UUID | None = None,
    department_id: UUID | None = None,
    search: str | None = None,
    overdue: bool = False,
    mine: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(require_permission("TICKETS_VIEW")),
) -> TicketListResponse:
    conn = await _connect()
    try:
        return await list_tickets(
            conn,
            actor=current_user,
            status=status,
            priority=priority,
            category_id=category_id,
            department_id=department_id,
            search=search,
            overdue=overdue,
            mine=mine,
            limit=limit,
            offset=offset,
        )
    finally:
        await conn.close()


@router.get("/export.csv")
async def export_tickets_csv_route(
    status: str | None = None,
    priority: str | None = None,
    category_id: UUID | None = None,
    department_id: UUID | None = None,
    search: str | None = None,
    overdue: bool = False,
    mine: bool = False,
    current_user: CurrentUser = Depends(require_permission("TICKETS_VIEW")),
) -> Response:
    conn = await _connect()
    try:
        body = await export_tickets_csv(
            conn,
            actor=current_user,
            status=status,
            priority=priority,
            category_id=category_id,
            department_id=department_id,
            search=search,
            overdue=overdue,
            mine=mine,
        )
    finally:
        await conn.close()
    return Response(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="tickets.csv"'},
    )


@router.get("/assignable-users", response_model=list[AssignableUser])
async def assignable_users_route() -> list[AssignableUser]:
    """Bilet atama seçicisi için — `GET /api/pam/users` `PAM_ADMIN`
    gerektirdiğinden `TICKETS_VIEW`-only bir kullanıcı onu çağıramaz;
    burada yalnızca id+kullanıcı adı (hassas alan yok) döneriz."""
    conn = await _connect()
    try:
        return [AssignableUser(id=row["id"], username=row["username"]) for row in await list_users(conn)]
    finally:
        await conn.close()


# ---- Faz 63 — Departman + Kategori taksonomisi ---------------------
# `GET` herkese (bilet oluşturma modalı için); `POST`/`DELETE` yalnızca
# ADMIN. İki tür şema olarak birebir aynı, tek bir yardımcı üzerinden.


async def _list_taxonomy(kind: str, include_inactive: bool) -> list[TicketTaxonomyItem]:
    conn = await _connect()
    try:
        return await list_taxonomy(conn, kind, include_inactive=include_inactive)
    finally:
        await conn.close()


async def _create_taxonomy(kind: str, name: str) -> TicketTaxonomyItem:
    conn = await _connect()
    try:
        return await create_taxonomy(conn, kind, name)
    except TaxonomyNameExistsError as exc:
        raise HTTPException(status_code=409, detail="Bu isimde aktif bir kayıt zaten var") from exc
    finally:
        await conn.close()


async def _deactivate_taxonomy(kind: str, item_id: UUID) -> TicketTaxonomyItem:
    conn = await _connect()
    try:
        return await deactivate_taxonomy(conn, kind, item_id)
    except TaxonomyItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Kayıt bulunamadı") from exc
    finally:
        await conn.close()


@router.get("/departments", response_model=list[TicketTaxonomyItem])
async def list_departments_route(include_inactive: bool = False) -> list[TicketTaxonomyItem]:
    return await _list_taxonomy("department", include_inactive)


@router.post("/departments", response_model=TicketTaxonomyItem, status_code=201, dependencies=[Depends(require_role("ADMIN"))])
async def create_department_route(payload: TicketTaxonomyCreateRequest) -> TicketTaxonomyItem:
    return await _create_taxonomy("department", payload.name)


@router.delete("/departments/{item_id}", response_model=TicketTaxonomyItem, dependencies=[Depends(require_role("ADMIN"))])
async def delete_department_route(item_id: UUID) -> TicketTaxonomyItem:
    return await _deactivate_taxonomy("department", item_id)


@router.get("/categories", response_model=list[TicketTaxonomyItem])
async def list_categories_route(include_inactive: bool = False) -> list[TicketTaxonomyItem]:
    return await _list_taxonomy("category", include_inactive)


@router.post("/categories", response_model=TicketTaxonomyItem, status_code=201, dependencies=[Depends(require_role("ADMIN"))])
async def create_category_route(payload: TicketTaxonomyCreateRequest) -> TicketTaxonomyItem:
    return await _create_taxonomy("category", payload.name)


@router.delete("/categories/{item_id}", response_model=TicketTaxonomyItem, dependencies=[Depends(require_role("ADMIN"))])
async def delete_category_route(item_id: UUID) -> TicketTaxonomyItem:
    return await _deactivate_taxonomy("category", item_id)


# ---- Faz 67 — SLA politikası -------------------------------------


class SlaPolicyUpdate(BaseModel):
    sla_hours: int = Field(ge=1, le=8760)


@router.get("/sla-policy", response_model=dict[str, int])
async def get_sla_policy_route() -> dict[str, int]:
    conn = await _connect()
    try:
        return await get_sla_policy(conn)
    finally:
        await conn.close()


@router.put("/sla-policy/{priority}", response_model=dict[str, int], dependencies=[Depends(require_role("ADMIN"))])
async def update_sla_policy_route(priority: str, payload: SlaPolicyUpdate) -> dict[str, int]:
    conn = await _connect()
    try:
        return await set_sla_policy(conn, priority.upper(), payload.sla_hours)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Geçersiz öncelik") from exc
    finally:
        await conn.close()


# ---- Faz 68 — salt-okunur metrikler ----------------------------


@router.get("/metrics", response_model=TicketMetricsResponse)
async def ticket_metrics_route(
    current_user: CurrentUser = Depends(require_permission("TICKETS_VIEW")),
) -> TicketMetricsResponse:
    conn = await _connect()
    try:
        return await get_metrics(conn, actor=current_user)
    finally:
        await conn.close()


@router.post("", response_model=TicketResponse, status_code=201)
async def create_ticket_route(
    payload: TicketCreateRequest, current_user: CurrentUser = Depends(require_permission("TICKETS_VIEW"))
) -> TicketResponse:
    conn = await _connect()
    try:
        return await create_ticket(conn, payload, created_by=current_user.id)
    except CategoryInvalidError as exc:
        raise HTTPException(status_code=400, detail="Geçersiz veya pasif kategori") from exc
    except DepartmentInvalidError as exc:
        raise HTTPException(status_code=400, detail="Geçersiz veya pasif departman") from exc
    finally:
        await conn.close()


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket_route(
    ticket_id: UUID, current_user: CurrentUser = Depends(require_permission("TICKETS_VIEW"))
) -> TicketResponse:
    conn = await _connect()
    try:
        return await get_ticket_detail(conn, ticket_id, actor=current_user)
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Bilet bulunamadı") from exc
    except TicketAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Bu bileti görüntüleme yetkiniz yok") from exc
    finally:
        await conn.close()


@router.post("/{ticket_id}/comments", response_model=TicketResponse)
async def add_comment_route(
    ticket_id: UUID,
    payload: TicketCommentCreateRequest,
    current_user: CurrentUser = Depends(require_permission("TICKETS_VIEW")),
) -> TicketResponse:
    conn = await _connect()
    try:
        return await add_comment(conn, ticket_id, payload, actor=current_user)
    except TicketNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Bilet bulunamadı") from exc
    except TicketAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Bu bilete erişim yetkiniz yok") from exc
    except AssigneeNotFoundError as exc:
        raise HTTPException(status_code=400, detail="Atanan kullanıcı bulunamadı") from exc
    except EmptyCommentError as exc:
        raise HTTPException(status_code=422, detail="body, status veya assigned_to alanlarından en az biri gerekli") from exc
    finally:
        await conn.close()
