"""Faz 55 — `/api/pam/server-groups` (`PAM_ADMIN` gerektirir). Bir
erişim kuralının TEK bir cihaz YERİNE statik bir cihaz grubuna
atanabilmesinin CRUD + üyelik yüzeyi — bkz. `app/pam/service.py`."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import CurrentUser, require_permission
from app.db.pam import get_connection
from app.pam.models import ServerGroupAssetSummary, ServerGroupCreateRequest, ServerGroupResponse, ServerGroupUpdateRequest
from app.pam.service import (
    ServerGroupInUseError,
    add_group_member,
    create_server_group,
    list_assets_for_group,
    list_server_groups,
    remove_group_member,
    update_server_group,
)
from app.pam.service import delete_server_group as delete_server_group_service

router = APIRouter(prefix="/api/pam/server-groups", tags=["pam"], dependencies=[Depends(require_permission("PAM_ADMIN"))])

logger = logging.getLogger(__name__)


async def _connect():
    try:
        return await get_connection()
    except OSError as exc:
        logger.warning("PostgreSQL erişilemedi (pam server groups)")
        raise HTTPException(status_code=503, detail={"database": "unreachable"}) from exc


@router.get("", response_model=list[ServerGroupResponse])
async def list_server_groups_route() -> list[ServerGroupResponse]:
    conn = await _connect()
    try:
        return await list_server_groups(conn)
    finally:
        await conn.close()


@router.post("", response_model=ServerGroupResponse, status_code=201)
async def create_server_group_route(
    payload: ServerGroupCreateRequest, current_user: CurrentUser = Depends(require_permission("PAM_ADMIN"))
) -> ServerGroupResponse:
    conn = await _connect()
    try:
        return await create_server_group(conn, payload, created_by=current_user.id)
    finally:
        await conn.close()


@router.put("/{server_group_id}", response_model=ServerGroupResponse)
async def update_server_group_route(server_group_id: UUID, payload: ServerGroupUpdateRequest) -> ServerGroupResponse:
    conn = await _connect()
    try:
        group = await update_server_group(conn, server_group_id, payload)
    finally:
        await conn.close()
    if group is None:
        raise HTTPException(status_code=404, detail="Cihaz grubu bulunamadı")
    return group


@router.delete("/{server_group_id}", status_code=204)
async def delete_server_group_route(server_group_id: UUID) -> None:
    conn = await _connect()
    try:
        try:
            deleted = await delete_server_group_service(conn, server_group_id)
        except ServerGroupInUseError as exc:
            raise HTTPException(
                status_code=409, detail="Bu cihaz grubu en az bir erişim kuralında kullanılıyor, önce onu kaldırın"
            ) from exc
    finally:
        await conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="Cihaz grubu bulunamadı")


@router.get("/{server_group_id}/assets", response_model=list[ServerGroupAssetSummary])
async def list_group_assets_route(server_group_id: UUID) -> list[ServerGroupAssetSummary]:
    conn = await _connect()
    try:
        rows = await list_assets_for_group(conn, server_group_id)
    finally:
        await conn.close()
    return [
        ServerGroupAssetSummary(id=row["id"], hostname=row["hostname"], ip_address=str(row["ip_address"]) if row["ip_address"] else None)
        for row in rows
    ]


@router.put("/{server_group_id}/assets/{asset_id}", status_code=204)
async def add_group_member_route(server_group_id: UUID, asset_id: UUID) -> None:
    conn = await _connect()
    try:
        await add_group_member(conn, server_group_id=server_group_id, asset_id=asset_id)
    finally:
        await conn.close()


@router.delete("/{server_group_id}/assets/{asset_id}", status_code=204)
async def remove_group_member_route(server_group_id: UUID, asset_id: UUID) -> None:
    conn = await _connect()
    try:
        await remove_group_member(conn, server_group_id=server_group_id, asset_id=asset_id)
    finally:
        await conn.close()
