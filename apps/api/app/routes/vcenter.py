"""Faz 72 — `/api/vcenter/*`: envanter (özet/VM/host) `VCENTER_VIEW`,
güç işlemleri `VCENTER_ADMIN` gerektirir (ikisi AYRI izin — bir
kullanıcı görüntüleyebilir ama başlatamayabilir)."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import require_permission
from app.db.vcenter import get_config as get_db_config
from app.db.vcenter import get_connection
from app.pam.vault import decrypt_payload
from app.vcenter.client import VCenterConnectError, VCenterConnectionParams
from app.vcenter.models import HostSummary, PowerActionRequest, VCenterSummary, VmDetail, VmSummary
from app.vcenter.service import get_summary, get_vm_detail, list_hosts, list_vms, power_action

router = APIRouter(prefix="/api/vcenter", tags=["vcenter"])

logger = logging.getLogger(__name__)


async def _connection_params() -> VCenterConnectionParams:
    try:
        conn = await get_connection()
    except OSError as exc:
        raise HTTPException(status_code=503, detail={"database": "unreachable"}) from exc
    try:
        row = await get_db_config(conn)
    finally:
        await conn.close()
    if row is None:
        raise HTTPException(status_code=409, detail="vCenter henüz yapılandırılmadı (bkz. Ayarlar)")
    return {
        "host": row["host"],
        "port": row["port"],
        "username": row["username"],
        "password": decrypt_payload(row["encrypted_password"])["password"],
        "verify_ssl": row["verify_ssl"],
    }


@router.get("/summary", response_model=VCenterSummary, dependencies=[Depends(require_permission("VCENTER_VIEW"))])
async def get_vcenter_summary_route() -> VCenterSummary:
    params = await _connection_params()
    try:
        return await get_summary(params)
    except VCenterConnectError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/vms", response_model=list[VmSummary], dependencies=[Depends(require_permission("VCENTER_VIEW"))])
async def list_vcenter_vms_route() -> list[VmSummary]:
    params = await _connection_params()
    try:
        return await list_vms(params)
    except VCenterConnectError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/vms/{vm_id}", response_model=VmDetail, dependencies=[Depends(require_permission("VCENTER_VIEW"))])
async def get_vcenter_vm_detail_route(vm_id: str) -> VmDetail:
    params = await _connection_params()
    try:
        return await get_vm_detail(params, vm_id)
    except VCenterConnectError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/hosts", response_model=list[HostSummary], dependencies=[Depends(require_permission("VCENTER_VIEW"))])
async def list_vcenter_hosts_route() -> list[HostSummary]:
    params = await _connection_params()
    try:
        return await list_hosts(params)
    except VCenterConnectError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/vms/{vm_id}/power", dependencies=[Depends(require_permission("VCENTER_ADMIN"))])
async def vcenter_vm_power_action_route(vm_id: str, payload: PowerActionRequest) -> dict:
    params = await _connection_params()
    try:
        await power_action(params, vm_id, payload.action)
    except VCenterConnectError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"status": "ok"}
