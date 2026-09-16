"""Faz 46/47 — `/api/pam/users`: sistem kullanıcı yönetimi. Tamamı
`require_permission("PAM_ADMIN")` arkasında — bu izne sahip olmayan
biri (OPERATOR/VIEWER varsayılan izin setinde YOK) başka bir
kullanıcının varlığını bile listeleyemez."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import require_permission
from app.auth.exceptions import AdUsernameNotFoundError, UsernameAlreadyExistsError
from app.auth.models import PermissionsUpdateRequest, UserCreateFromAdRequest, UserCreateRequest, UserResponse, UserUpdateRequest
from app.auth.service import apply_user_update, create_user, get_user, import_user_from_ad, list_all_users, set_user_permissions
from app.db.users import get_connection
from app.services.ldap_auth import AdUserAlreadyLinkedError, AdUserNotFoundError

router = APIRouter(prefix="/api/pam/users", tags=["pam"], dependencies=[Depends(require_permission("PAM_ADMIN"))])

logger = logging.getLogger(__name__)


async def _connect():
    try:
        return await get_connection()
    except OSError as exc:
        logger.warning("PostgreSQL erişilemedi (pam users)")
        raise HTTPException(status_code=503, detail={"database": "unreachable"}) from exc


@router.get("", response_model=list[UserResponse])
async def list_users_route() -> list[UserResponse]:
    conn = await _connect()
    try:
        return await list_all_users(conn)
    finally:
        await conn.close()


@router.post("", response_model=UserResponse, status_code=201)
async def create_user_route(payload: UserCreateRequest) -> UserResponse:
    conn = await _connect()
    try:
        return await create_user(conn, payload)
    except UsernameAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail="Bu kullanıcı adı zaten kullanımda") from exc
    finally:
        await conn.close()


@router.post("/from-ad", response_model=UserResponse, status_code=201)
async def create_user_from_ad_route(payload: UserCreateFromAdRequest) -> UserResponse:
    """Faz 52 — "Active Directory'den İçe Aktar". `UserCreateRequest`
    (yerel) ile AYNI endpoint'e (`POST ""`) BİLİNÇLİ olarak eklenmedi —
    iki akışın gövde şekli (parola VAR/YOK) yeterince farklı, ayrı bir
    route daha net."""
    conn = await _connect()
    try:
        return await import_user_from_ad(conn, ad_username=payload.ad_username, role=payload.role)
    except AdUserNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Belirtilen AD kullanıcı adı senkronize edilmiş kayıtlarda bulunamadı") from exc
    except AdUserAlreadyLinkedError as exc:
        raise HTTPException(status_code=409, detail="Bu AD hesabı zaten bir yerel kullanıcıya bağlı") from exc
    finally:
        await conn.close()


@router.get("/{user_id}", response_model=UserResponse)
async def get_user_route(user_id: UUID) -> UserResponse:
    conn = await _connect()
    try:
        user = await get_user(conn, user_id)
    finally:
        await conn.close()
    if user is None:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_user_route(user_id: UUID, payload: UserUpdateRequest) -> UserResponse:
    conn = await _connect()
    try:
        user = await apply_user_update(conn, user_id, payload)
    except AdUsernameNotFoundError as exc:
        raise HTTPException(status_code=422, detail="Belirtilen AD kullanıcı adı senkronize edilmiş kayıtlarda bulunamadı") from exc
    finally:
        await conn.close()
    if user is None:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    return user


@router.put("/{user_id}/permissions", response_model=UserResponse)
async def update_user_permissions_route(user_id: UUID, payload: PermissionsUpdateRequest) -> UserResponse:
    """Faz 47 — kullanıcının TAM izin setini değiştirir (bkz. `app/db/
    users.py::set_permissions` — ekleme değil, yer değiştirme). Admin
    panelindeki "Yetkiler" checkbox matrisinin karşılığı; bir kullanıcıyı
    Dashboard dahil her genel menüden mahrum bırakıp yalnızca
    `PAM_ACCESS` bırakmak da (kullanıcının açık örneği) bununla mümkün."""
    conn = await _connect()
    try:
        user = await set_user_permissions(conn, user_id, payload)
    finally:
        await conn.close()
    if user is None:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    return user
