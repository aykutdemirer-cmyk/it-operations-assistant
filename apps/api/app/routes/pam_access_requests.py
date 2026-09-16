"""Faz 56 — `/api/pam/access-requests` (`PAM_ADMIN` gerektirir: listeleme
+ onay/red) + `/api/pam/access-requests` (`PAM_ACCESS` gerektirir: talep
açma + kendi taleplerini görme, `my_router`). Onaylama YENİ bir
yetkilendirme mekanizması AÇMAZ — mevcut `pam_access_rules`'u genişletir/
oluşturur, bkz. `app/pam/service.py::approve_access_request`."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import CurrentUser, require_permission
from app.db.pam import get_connection
from app.pam.models import (
    AccessRequestApproveRequest,
    AccessRequestCreateRequest,
    AccessRequestRejectRequest,
    AccessRequestResponse,
)
from app.pam.service import (
    AccessRequestNotFoundError,
    AccessRequestNotPendingError,
    approve_access_request,
    create_access_request,
    list_access_requests,
    reject_access_request,
)

router = APIRouter(
    prefix="/api/pam/access-requests", tags=["pam"], dependencies=[Depends(require_permission("PAM_ADMIN"))]
)
# Faz 51/pam_rules.py'deki `my_access_router` ile AYNI gerekçe — bir
# kullanıcının KENDİ talebini açması/görmesi `PAM_ADMIN` DEĞİL,
# `PAM_ACCESS` gerektirir (router-seviyesi bağımlılık farklı olduğu
# için AYRI bir router).
my_router = APIRouter(prefix="/api/pam/access-requests", tags=["pam"])

logger = logging.getLogger(__name__)


async def _connect():
    try:
        return await get_connection()
    except OSError as exc:
        logger.warning("PostgreSQL erişilemedi (pam access requests)")
        raise HTTPException(status_code=503, detail={"database": "unreachable"}) from exc


@router.get("", response_model=list[AccessRequestResponse])
async def list_access_requests_route(status: str | None = None) -> list[AccessRequestResponse]:
    conn = await _connect()
    try:
        return await list_access_requests(conn, status=status)
    finally:
        await conn.close()


@router.post("/{request_id}/approve", response_model=AccessRequestResponse)
async def approve_access_request_route(
    request_id: UUID,
    payload: AccessRequestApproveRequest,
    current_user: CurrentUser = Depends(require_permission("PAM_ADMIN")),
) -> AccessRequestResponse:
    conn = await _connect()
    try:
        try:
            return await approve_access_request(conn, request_id, payload, reviewed_by=current_user.id)
        except AccessRequestNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Erişim talebi bulunamadı") from exc
        except AccessRequestNotPendingError as exc:
            raise HTTPException(status_code=409, detail="Bu talep zaten incelenmiş") from exc
    finally:
        await conn.close()


@router.post("/{request_id}/reject", response_model=AccessRequestResponse)
async def reject_access_request_route(
    request_id: UUID,
    payload: AccessRequestRejectRequest,
    current_user: CurrentUser = Depends(require_permission("PAM_ADMIN")),
) -> AccessRequestResponse:
    conn = await _connect()
    try:
        try:
            return await reject_access_request(conn, request_id, payload, reviewed_by=current_user.id)
        except AccessRequestNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Erişim talebi bulunamadı") from exc
        except AccessRequestNotPendingError as exc:
            raise HTTPException(status_code=409, detail="Bu talep zaten incelenmiş") from exc
    finally:
        await conn.close()


@my_router.post("", response_model=AccessRequestResponse, status_code=201)
async def create_access_request_route(
    payload: AccessRequestCreateRequest, current_user: CurrentUser = Depends(require_permission("PAM_ACCESS"))
) -> AccessRequestResponse:
    conn = await _connect()
    try:
        return await create_access_request(conn, payload, requester_id=current_user.id)
    finally:
        await conn.close()


@my_router.get("/mine", response_model=list[AccessRequestResponse])
async def list_my_access_requests_route(current_user: CurrentUser = Depends(require_permission("PAM_ACCESS"))) -> list[AccessRequestResponse]:
    conn = await _connect()
    try:
        return await list_access_requests(conn, requester_id=current_user.id)
    finally:
        await conn.close()
