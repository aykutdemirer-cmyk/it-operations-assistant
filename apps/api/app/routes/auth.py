"""Faz 46 — `POST /api/auth/login` + `GET /api/auth/me`. Bu iki endpoint
auth yok/gerekli değil sözleşmesinin istisnası DEĞİL — `login` zaten
kimlik doğrulamanın kendisi, `me` mevcut bir token'ı doğrulamak için
`get_current_user`'ı kullanır (bkz. `app/auth/dependencies.py`)."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import CurrentUser, get_current_user
from app.auth.exceptions import InvalidCredentialsError, UserInactiveError
from app.auth.models import LoginRequest, TokenResponse, UserResponse
from app.auth.service import get_user, login
from app.db.users import get_connection

router = APIRouter(prefix="/api/auth", tags=["auth"])

logger = logging.getLogger(__name__)


@router.post("/login", response_model=TokenResponse)
async def login_route(payload: LoginRequest) -> TokenResponse:
    try:
        conn = await get_connection()
    except OSError:
        raise HTTPException(status_code=503, detail={"database": "unreachable"})
    try:
        token, expires_in, user = await login(conn, username=payload.username, password=payload.password)
    except (InvalidCredentialsError, UserInactiveError):
        # İkisi de AYNI 401 mesajıyla döner — hesabın var olup
        # olmadığını/aktif olup olmadığını dışarıdan ayırt ettirmez.
        raise HTTPException(status_code=401, detail="Kullanıcı adı veya parola hatalı")
    finally:
        await conn.close()

    return TokenResponse(access_token=token, expires_in_seconds=expires_in, user=user)


@router.get("/me", response_model=UserResponse)
async def me_route(current_user: CurrentUser = Depends(get_current_user)) -> UserResponse:
    try:
        conn = await get_connection()
    except OSError:
        raise HTTPException(status_code=503, detail={"database": "unreachable"})
    try:
        user = await get_user(conn, current_user.id)
    finally:
        await conn.close()

    if user is None:
        raise HTTPException(status_code=401, detail="Kullanıcı bulunamadı")
    return user
