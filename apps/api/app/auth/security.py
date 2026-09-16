"""Faz 46 — parola hash'leme (bcrypt) + oturum token'ı imzalama/
doğrulama (PyJWT). İki anahtar TAMAMEN ayrı ve her ikisi de yalnızca
`.env`'den okunur (bkz. CLAUDE.md güvenlik kuralı — sırlar asla kodda/
loglarda):

- `JWT_SECRET_KEY` — bu modülün token imzası. Eksikse süreç KASITLI
  olarak import sırasında çöker (üretimde sessizce zayıf/varsayılan bir
  anahtarla imzalamak, `PAM_VAULT_SECRET_KEY` eksikliğinden çok daha
  geniş bir yetki yükseltme riski taşır — her istek bu anahtara güvenir).
- `PAM_VAULT_SECRET_KEY` — bu modülde YOK, bkz. `app/pam/vault.py`."""

import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

import bcrypt
import jwt

from app.auth.exceptions import InvalidTokenError

_JWT_ALGORITHM = "HS256"
_TOKEN_TTL_MINUTES = int(os.environ.get("JWT_TOKEN_TTL_MINUTES", "480"))


def _jwt_secret_key() -> str:
    key = os.environ.get("JWT_SECRET_KEY")
    if not key:
        raise RuntimeError(
            "JWT_SECRET_KEY .env içinde tanımlı değil — oturum token'ları "
            "imzalanamaz (bkz. apps/api/.env.example)."
        )
    return key


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # Bozuk/eski formatlı bir hash — kimlik doğrulaması reddedilir,
        # exception dışarı sızmaz.
        return False


def create_access_token(*, user_id: UUID, username: str, role: str) -> tuple[str, int]:
    """`(token, expires_in_seconds)` döner. Payload minimal — yalnızca
    kimlik doğrulama/yetkilendirme için gereken 3 alan, hiçbir hassas
    veri taşımaz."""
    ttl_seconds = _TOKEN_TTL_MINUTES * 60
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
    }
    token = jwt.encode(payload, _jwt_secret_key(), algorithm=_JWT_ALGORITHM)
    return token, ttl_seconds


def decode_access_token(token: str) -> dict:
    """Geçersiz/süresi dolmuş bir token için her zaman
    `InvalidTokenError` fırlatır — çağıran taraf (`app/auth/
    dependencies.py`) bunu tek bir 401'e çevirir, ham PyJWT
    exception'ı asla dışarı sızmaz."""
    try:
        return jwt.decode(token, _jwt_secret_key(), algorithms=[_JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
