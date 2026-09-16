"""Faz 46/47 — login/kullanıcı CRUD orkestrasyon katmanı. Route katmanı
(`app/routes/auth.py`/`app/routes/pam_users.py`) yalnızca HTTP
sözleşmesiyle ilgilenir, iş kuralları burada yaşar."""

from uuid import UUID

import asyncpg

from app.auth.exceptions import AdUsernameNotFoundError, InvalidCredentialsError, UsernameAlreadyExistsError, UserInactiveError
from app.auth.models import PermissionsUpdateRequest, UserCreateRequest, UserResponse, UserUpdateRequest
from app.auth.permissions import default_permissions_for_role
from app.auth.security import create_access_token, hash_password, verify_password
from app.db.users import get_permissions, get_user_by_username, insert_user, list_users, set_permissions, update_user
from app.db.users import get_user_by_id as _get_user_by_id
from app.services.ldap_auth import authenticate_and_provision, create_user_from_ad


async def _to_response(conn: asyncpg.Connection, row: asyncpg.Record) -> UserResponse:
    permissions = await get_permissions(conn, row["id"])
    return UserResponse(
        id=row["id"],
        username=row["username"],
        role=row["role"],
        full_name=row["full_name"],
        is_active=row["is_active"],
        ad_username=row["ad_username"],
        ticket_role=row["ticket_role"] if "ticket_role" in row else "REQUESTER",
        permissions=permissions,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def login(conn: asyncpg.Connection, *, username: str, password: str) -> tuple[str, int, UserResponse]:
    row = await get_user_by_username(conn, username)
    # Yerel şifre yalnızca DOLU bir `password_hash` varsa kontrol edilir
    # — AD-provizyonlu bir kullanıcının (Faz 52) `password_hash`'i
    # KASITLI olarak NULL, `verify_password`'a hiç geçirilmez (None
    # üzerinde `.encode()` çağrısı bir AttributeError fırlatırdı).
    local_ok = row is not None and row["password_hash"] is not None and verify_password(password, row["password_hash"])

    if not local_ok:
        # Faz 52 — yerel eşleşme yoksa (opt-in) LDAP bind dener; bu
        # `LDAP_AUTH_ENABLED=false` (varsayılan) iken HER ZAMAN `None`
        # döner, davranış Faz 46'dan beri DEĞİŞMEDİ. Kullanıcı adı yok/
        # parola yanlış/LDAP kapalı/bind başarısız — HEPSİ AYNI genel
        # hatayla döner (enumeration'ı önlemek için kasıtlı, bkz. app/
        # auth/exceptions.py).
        row = await authenticate_and_provision(conn, username=username, password=password)
        if row is None:
            raise InvalidCredentialsError()

    if not row["is_active"]:
        raise UserInactiveError()

    token, expires_in = create_access_token(user_id=row["id"], username=row["username"], role=row["role"])
    return token, expires_in, await _to_response(conn, row)


async def create_user(conn: asyncpg.Connection, payload: UserCreateRequest) -> UserResponse:
    existing = await get_user_by_username(conn, payload.username)
    if existing is not None:
        raise UsernameAlreadyExistsError()

    row = await insert_user(
        conn,
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        full_name=payload.full_name,
        ticket_role=payload.ticket_role,
    )
    # Yeni kullanıcı rolüne göre bir VARSAYILAN izin setiyle başlar —
    # admin bunu istediği zaman `set_user_permissions` ile değiştirebilir
    # (bkz. app/auth/permissions.py — kalıcı bir kısıt değil, yalnızca
    # makul bir başlangıç noktası).
    await set_permissions(conn, row["id"], default_permissions_for_role(payload.role))
    return await _to_response(conn, row)


async def import_user_from_ad(conn: asyncpg.Connection, *, ad_username: str, role: str) -> UserResponse:
    """Faz 52 — `/pam/users`'ın "Active Directory'den İçe Aktar" akışı
    için ince bir sarmalayıcı — asıl mantık `app/services/ldap_auth.py::
    create_user_from_ad`'da (LDAP servisiyle ilgili KOD orada toplu
    kalsın diye, bu modül yalnızca `UserResponse`'a çeviriyor)."""
    row = await create_user_from_ad(conn, ad_username=ad_username, role=role)
    return await _to_response(conn, row)


async def get_user(conn: asyncpg.Connection, user_id: UUID) -> UserResponse | None:
    row = await _get_user_by_id(conn, user_id)
    return await _to_response(conn, row) if row is not None else None


async def list_all_users(conn: asyncpg.Connection) -> list[UserResponse]:
    rows = await list_users(conn)
    return [await _to_response(conn, row) for row in rows]


async def apply_user_update(conn: asyncpg.Connection, user_id: UUID, payload: UserUpdateRequest) -> UserResponse | None:
    unset_fields = payload.model_fields_set
    password_hash = hash_password(payload.password) if payload.password else None
    try:
        row = await update_user(
            conn,
            user_id,
            role=payload.role,
            full_name=payload.full_name,
            is_active=payload.is_active,
            password_hash=password_hash,
            ad_username=payload.ad_username,
            ticket_role=payload.ticket_role,
            _unset=unset_fields,
        )
    except asyncpg.ForeignKeyViolationError as exc:
        raise AdUsernameNotFoundError() from exc
    return await _to_response(conn, row) if row is not None else None


async def set_user_permissions(conn: asyncpg.Connection, user_id: UUID, payload: PermissionsUpdateRequest) -> UserResponse | None:
    row = await _get_user_by_id(conn, user_id)
    if row is None:
        return None
    await set_permissions(conn, user_id, list(payload.permissions))
    return await _to_response(conn, row)
