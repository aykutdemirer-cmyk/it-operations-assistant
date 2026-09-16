"""Faz 72 — `/api/settings/vcenter`: vCenter/vSphere bağlantı
yapılandırması. `VCENTER_ADMIN` gerektirir — hassas bir bağlantı bilgisi
(parola) taşıdığı için `app/routes/ldap_settings.py`'nin `PAM_ADMIN`
sınırıyla AYNI ilke, yalnızca izin adı farklı."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import require_permission
from app.db.vcenter import get_config, get_connection, record_test_result, upsert_config
from app.pam.vault import decrypt_payload, encrypt_payload
from app.vcenter.client import VCenterConnectError, VCenterConnectionParams
from app.vcenter.models import VCenterConfigRequest, VCenterConfigResponse, VCenterTestResult
from app.vcenter.service import test_connection

router = APIRouter(
    prefix="/api/settings/vcenter", tags=["vcenter-settings"], dependencies=[Depends(require_permission("VCENTER_ADMIN"))]
)

logger = logging.getLogger(__name__)


async def _connect():
    try:
        return await get_connection()
    except OSError as exc:
        logger.warning("PostgreSQL erişilemedi (vcenter settings)")
        raise HTTPException(status_code=503, detail={"database": "unreachable"}) from exc


def _to_response(row) -> VCenterConfigResponse:
    return VCenterConfigResponse(
        host=row["host"],
        port=row["port"],
        username=row["username"],
        verify_ssl=row["verify_ssl"],
        last_test_status=row["last_test_status"],
        last_test_error=row["last_test_error"],
        last_test_at=row["last_test_at"],
        updated_at=row["updated_at"],
    )


async def _existing_config_or_422(conn) -> object:
    existing = await get_config(conn)
    if existing is None:
        raise HTTPException(status_code=422, detail="Parola ilk kayıtta zorunludur")
    return existing


async def _resolve_password(conn, payload: VCenterConfigRequest) -> str:
    if payload.password:
        return payload.password
    existing = await _existing_config_or_422(conn)
    return decrypt_payload(existing["encrypted_password"])["password"]


async def _resolve_encrypted_password(conn, payload: VCenterConfigRequest) -> str:
    """`PUT`'a özel: parola boş bırakılırsa kayıtlı şifreli değeri
    decrypt+reencrypt YAPMADAN korur — `ldap_settings.py::_resolve_
    encrypted_bind_password` ile AYNI ilke."""
    if payload.password:
        return encrypt_payload({"password": payload.password})
    existing = await _existing_config_or_422(conn)
    return existing["encrypted_password"]


def _connection_params(payload: VCenterConfigRequest, *, password: str) -> VCenterConnectionParams:
    return {
        "host": payload.host,
        "port": payload.port,
        "username": payload.username,
        "password": password,
        "verify_ssl": payload.verify_ssl,
    }


@router.get("", response_model=VCenterConfigResponse | None)
async def get_vcenter_config_route() -> VCenterConfigResponse | None:
    conn = await _connect()
    try:
        row = await get_config(conn)
    finally:
        await conn.close()
    return _to_response(row) if row is not None else None


@router.put("", response_model=VCenterConfigResponse)
async def update_vcenter_config_route(payload: VCenterConfigRequest) -> VCenterConfigResponse:
    conn = await _connect()
    try:
        encrypted_password = await _resolve_encrypted_password(conn, payload)
        row = await upsert_config(
            conn,
            host=payload.host,
            port=payload.port,
            username=payload.username,
            encrypted_password=encrypted_password,
            verify_ssl=payload.verify_ssl,
        )
    finally:
        await conn.close()
    return _to_response(row)


@router.post("/test", response_model=VCenterTestResult)
async def test_vcenter_connection_route(payload: VCenterConfigRequest) -> VCenterTestResult:
    """Girilen (henüz KAYDEDİLMEMİŞ olabilecek) parametrelerle GERÇEK bir
    vCenter oturumu açmayı dener — "Bağlantıyı Test Et" butonu. Parola
    boş bırakılırsa kayıtlı yapılandırmanın parolasıyla test eder."""
    conn = await _connect()
    try:
        password = await _resolve_password(conn, payload)
        params = _connection_params(payload, password=password)
        try:
            await test_connection(params)
            await record_test_result(conn, status="success", error=None)
            return VCenterTestResult(success=True, message="Bağlantı başarılı")
        except VCenterConnectError as exc:
            await record_test_result(conn, status="error", error=str(exc))
            return VCenterTestResult(success=False, message=str(exc))
    finally:
        await conn.close()
