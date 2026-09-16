"""Faz 46/47 — `/api/pam/rules` (`PAM_ADMIN` gerektirir) + `/api/pam/
my-access` (`PAM_ACCESS` gerektirir — kendisine atanmış sunucuları
görür)."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import CurrentUser, require_permission
from app.db.pam import get_connection
from app.pam.models import AuthorizedAssetResponse, PamAccessRuleCreateRequest, PamAccessRuleResponse, PamAccessRuleUpdateRequest
from app.pam.service import RuleAlreadyExistsError, create_rule, delete_rule, list_authorized_assets_for_user, list_rules, update_rule

router = APIRouter(prefix="/api/pam/rules", tags=["pam"], dependencies=[Depends(require_permission("PAM_ADMIN"))])
my_access_router = APIRouter(prefix="/api/pam", tags=["pam"])

logger = logging.getLogger(__name__)


async def _connect():
    try:
        return await get_connection()
    except OSError as exc:
        logger.warning("PostgreSQL erişilemedi (pam rules)")
        raise HTTPException(status_code=503, detail={"database": "unreachable"}) from exc


@router.get("", response_model=list[PamAccessRuleResponse])
async def list_rules_route(
    search: str | None = None, limit: int | None = None, offset: int | None = None
) -> list[PamAccessRuleResponse]:
    """Faz 54 — `search` (kullanıcı/AD grubu/cihaz/kasa hesabı adında
    serbest metin arama), `limit`/`offset` (sayfalama) hepsi opsiyonel —
    hiçbiri verilmezse Faz 46'daki davranışla birebir aynı, TÜM
    kuralları döner."""
    conn = await _connect()
    try:
        return await list_rules(conn, search=search, limit=limit, offset=offset)
    finally:
        await conn.close()


@router.post("", response_model=PamAccessRuleResponse, status_code=201)
async def create_rule_route(
    payload: PamAccessRuleCreateRequest, current_user: CurrentUser = Depends(require_permission("PAM_ADMIN"))
) -> PamAccessRuleResponse:
    conn = await _connect()
    try:
        return await create_rule(conn, payload, created_by=current_user.id)
    except RuleAlreadyExistsError as exc:
        raise HTTPException(
            status_code=409, detail="Bu kullanıcı için bu asset'e zaten bir kural var — mevcut kuralı düzenleyin"
        ) from exc
    finally:
        await conn.close()


@router.put("/{rule_id}", response_model=PamAccessRuleResponse)
async def update_rule_route(rule_id: UUID, payload: PamAccessRuleUpdateRequest) -> PamAccessRuleResponse:
    conn = await _connect()
    try:
        rule = await update_rule(conn, rule_id, payload)
    finally:
        await conn.close()
    if rule is None:
        raise HTTPException(status_code=404, detail="Erişim kuralı bulunamadı")
    return rule


@router.delete("/{rule_id}", status_code=204)
async def delete_rule_route(rule_id: UUID) -> None:
    conn = await _connect()
    try:
        deleted = await delete_rule(conn, rule_id)
    finally:
        await conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="Erişim kuralı bulunamadı")


@my_access_router.get("/my-access", response_model=list[AuthorizedAssetResponse])
async def my_access_route(current_user: CurrentUser = Depends(require_permission("PAM_ACCESS"))) -> list[AuthorizedAssetResponse]:
    conn = await _connect()
    try:
        return await list_authorized_assets_for_user(conn, current_user.id)
    finally:
        await conn.close()
