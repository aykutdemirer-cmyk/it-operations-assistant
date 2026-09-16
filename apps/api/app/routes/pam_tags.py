"""Faz 55 — `/api/pam/tags` (`PAM_ADMIN` gerektirir). Bir erişim
kuralının TEK bir cihaz YERİNE bir etikete atanabilmesinin CRUD +
atama/kaldırma yüzeyi — bkz. `app/pam/service.py`."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import CurrentUser, require_permission
from app.db.pam import get_connection
from app.pam.models import TagAssetSummary, TagCreateRequest, TagResponse
from app.pam.service import TagInUseError, assign_tag, create_tag, list_assets_for_tag, list_tags, unassign_tag
from app.pam.service import delete_tag as delete_tag_service

router = APIRouter(prefix="/api/pam/tags", tags=["pam"], dependencies=[Depends(require_permission("PAM_ADMIN"))])

logger = logging.getLogger(__name__)


async def _connect():
    try:
        return await get_connection()
    except OSError as exc:
        logger.warning("PostgreSQL erişilemedi (pam tags)")
        raise HTTPException(status_code=503, detail={"database": "unreachable"}) from exc


@router.get("", response_model=list[TagResponse])
async def list_tags_route() -> list[TagResponse]:
    conn = await _connect()
    try:
        return await list_tags(conn)
    finally:
        await conn.close()


@router.post("", response_model=TagResponse, status_code=201)
async def create_tag_route(
    payload: TagCreateRequest, current_user: CurrentUser = Depends(require_permission("PAM_ADMIN"))
) -> TagResponse:
    conn = await _connect()
    try:
        return await create_tag(conn, payload, created_by=current_user.id)
    finally:
        await conn.close()


@router.delete("/{tag_id}", status_code=204)
async def delete_tag_route(tag_id: UUID) -> None:
    conn = await _connect()
    try:
        try:
            deleted = await delete_tag_service(conn, tag_id)
        except TagInUseError as exc:
            raise HTTPException(status_code=409, detail="Bu etiket en az bir erişim kuralında kullanılıyor, önce onu kaldırın") from exc
    finally:
        await conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="Etiket bulunamadı")


@router.get("/{tag_id}/assets", response_model=list[TagAssetSummary])
async def list_tag_assets_route(tag_id: UUID) -> list[TagAssetSummary]:
    conn = await _connect()
    try:
        rows = await list_assets_for_tag(conn, tag_id)
    finally:
        await conn.close()
    return [TagAssetSummary(id=row["id"], hostname=row["hostname"], ip_address=str(row["ip_address"]) if row["ip_address"] else None) for row in rows]


@router.put("/{tag_id}/assets/{asset_id}", status_code=204)
async def assign_tag_route(tag_id: UUID, asset_id: UUID) -> None:
    conn = await _connect()
    try:
        await assign_tag(conn, tag_id=tag_id, asset_id=asset_id)
    finally:
        await conn.close()


@router.delete("/{tag_id}/assets/{asset_id}", status_code=204)
async def unassign_tag_route(tag_id: UUID, asset_id: UUID) -> None:
    conn = await _connect()
    try:
        await unassign_tag(conn, tag_id=tag_id, asset_id=asset_id)
    finally:
        await conn.close()
