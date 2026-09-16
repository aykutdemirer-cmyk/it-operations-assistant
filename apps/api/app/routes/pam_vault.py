"""Faz 46 — `/api/pam/vault`: kimlik bilgisi kasası. Tamamı
`require_role("ADMIN")` arkasında. Liste/detay endpoint'leri her zaman
maskelenmiş (`VaultCredentialResponse`) döner — gerçek değer yalnızca
ayrı `POST .../{id}/reveal` ile, GERÇEK bir Admin isteğinde döner
(kullanıcının "Show/Hide" gereksinimi)."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import CurrentUser, require_permission
from app.db.pam import get_connection
from app.pam.models import (
    VaultCredentialCreateRequest,
    VaultCredentialRevealResponse,
    VaultCredentialResponse,
    VaultCredentialUpdateRequest,
)
from app.pam.service import CredentialInUseError, create_credential, delete_credential, list_credentials, reveal_credential, update_credential

router = APIRouter(prefix="/api/pam/vault", tags=["pam"], dependencies=[Depends(require_permission("PAM_ADMIN"))])

logger = logging.getLogger(__name__)


async def _connect():
    try:
        return await get_connection()
    except OSError as exc:
        logger.warning("PostgreSQL erişilemedi (pam vault)")
        raise HTTPException(status_code=503, detail={"database": "unreachable"}) from exc


@router.get("", response_model=list[VaultCredentialResponse])
async def list_credentials_route() -> list[VaultCredentialResponse]:
    conn = await _connect()
    try:
        return await list_credentials(conn)
    finally:
        await conn.close()


@router.post("", response_model=VaultCredentialResponse, status_code=201)
async def create_credential_route(
    payload: VaultCredentialCreateRequest, current_user: CurrentUser = Depends(require_permission("PAM_ADMIN"))
) -> VaultCredentialResponse:
    conn = await _connect()
    try:
        return await create_credential(conn, payload, created_by=current_user.id)
    finally:
        await conn.close()


@router.put("/{credential_id}", response_model=VaultCredentialResponse)
async def update_credential_route(credential_id: UUID, payload: VaultCredentialUpdateRequest) -> VaultCredentialResponse:
    conn = await _connect()
    try:
        credential = await update_credential(conn, credential_id, payload)
    finally:
        await conn.close()
    if credential is None:
        raise HTTPException(status_code=404, detail="Kasa hesabı bulunamadı")
    return credential


@router.delete("/{credential_id}", status_code=204)
async def delete_credential_route(credential_id: UUID) -> None:
    conn = await _connect()
    try:
        deleted = await delete_credential(conn, credential_id)
    except CredentialInUseError as exc:
        raise HTTPException(
            status_code=409, detail="Bu kasa hesabı bir veya daha fazla erişim kuralında kullanılıyor"
        ) from exc
    finally:
        await conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="Kasa hesabı bulunamadı")


@router.post("/{credential_id}/reveal", response_model=VaultCredentialRevealResponse)
async def reveal_credential_route(credential_id: UUID) -> VaultCredentialRevealResponse:
    conn = await _connect()
    try:
        credential = await reveal_credential(conn, credential_id)
    finally:
        await conn.close()
    if credential is None:
        raise HTTPException(status_code=404, detail="Kasa hesabı bulunamadı")
    return credential
