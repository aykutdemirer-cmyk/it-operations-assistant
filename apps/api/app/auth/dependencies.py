"""Faz 46 — FastAPI `Depends` tabanlı auth/RBAC koruması. Her korumalı
route bu modüldeki `get_current_user`/`require_role(...)`'u kullanır;
JWT doğrulama + `is_active` kontrolü tek bir yerde yaşar, route'lar
kendi ad-hoc header parsing'ini YAZMAZ."""

from uuid import UUID

from fastapi import Depends, Header, HTTPException

from app.auth.exceptions import InvalidTokenError
from app.auth.models import UserRole
from app.auth.permissions import Permission
from app.auth.security import decode_access_token
from app.db.users import get_connection, get_permissions, get_user_by_id


class CurrentUser:
    """Route katmanına geçirilen minimal, doğrulanmış kullanıcı kimliği.
    `permissions` HER İSTEKTE DB'den taze okunur (JWT payload'ında
    SAKLANMAZ) — bkz. `app/auth/models.py::UserResponse` docstring'i."""

    def __init__(
        self, *, id: UUID, username: str, role: UserRole, permissions: list[Permission], ticket_role: str = "REQUESTER"
    ) -> None:
        self.id = id
        self.username = username
        self.role = role
        self.permissions = permissions
        # Faz 65 — bilet-modülü RBAC: TECHNICIAN/ADMIN tüm biletleri
        # görür, REQUESTER yalnızca kendi açtıklarını.
        self.ticket_role = ticket_role


async def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Oturum token'ı gerekli")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Oturum token'ı gerekli")

    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        raise HTTPException(status_code=401, detail="Oturum token'ı geçersiz veya süresi dolmuş")

    user_id = UUID(payload["sub"])

    # Token geçerli olsa bile kullanıcı sonradan devre dışı bırakılmış/
    # silinmiş olabilir — her istekte DB'den taze kontrol edilir
    # (mevcut Faz 28 Bearer-auth deseniyle aynı ilke: kısa ömürlü
    # token + her istekte gerçek durum kontrolü).
    try:
        conn = await get_connection()
    except OSError:
        raise HTTPException(status_code=503, detail={"database": "unreachable"})
    try:
        row = await get_user_by_id(conn, user_id)
        if row is None or not row["is_active"]:
            raise HTTPException(status_code=401, detail="Kullanıcı bulunamadı veya devre dışı")
        permissions = await get_permissions(conn, row["id"])
    finally:
        await conn.close()

    return CurrentUser(
        id=row["id"],
        username=row["username"],
        role=row["role"],
        permissions=permissions,
        ticket_role=row["ticket_role"] if "ticket_role" in row else "REQUESTER",
    )


def require_role(*allowed_roles: UserRole):
    """`Depends(require_role("ADMIN"))` gibi kullanılır. Rol yetersizse
    403 (401 DEĞİL — kimlik zaten doğrulandı, yalnızca yetki yetersiz).
    Faz 47'den itibaren yeni route'lar için `require_permission(...)`
    tercih edilir — bu, geriye dönük uyumluluk/yalnızca-rol-yeterli
    olan az sayıdaki durum için duruyor."""

    async def _dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Bu işlem için yeterli yetkiniz yok")
        return current_user

    return _dependency


def require_permission(*any_of: Permission):
    """`Depends(require_permission("PAM_ADMIN"))` gibi kullanılır —
    kullanıcının `any_of` listesindeki izinlerden EN AZ BİRİNE sahip
    olması yeterli. Faz 47'nin ince taneli yetkilendirmesinin asıl
    uygulama noktası; `require_role`'ün YERİNİ ALIYOR (yeni PAM
    route'ları bunu kullanıyor)."""

    async def _dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not any(p in current_user.permissions for p in any_of):
            raise HTTPException(status_code=403, detail="Bu işlem için yeterli yetkiniz yok")
        return current_user

    return _dependency
