"""Agent bearer token üretimi/hash'lenmesi/doğrulanması (Faz 28).

Model: agent kayıt olduğunda sunucu yüksek entropili rastgele bir token
üretir (`secrets.token_urlsafe(32)`, 256 bit) ve YALNIZCA O AN
`AgentRegistrationResponse.token` içinde döner — bir daha asla
görünmez. DB'de yalnızca SHA-256 hash'i (`agents.token_hash`) saklanır.

Neden SHA-256 (bcrypt/argon2 DEĞİL): bcrypt/argon2, düşük entropili
İNSAN parolalarına karşı brute-force'u yavaşlatmak için var — burada
token zaten 256 bit rastgele (insan tahmin edemez), yavaş hash
gereksiz bir performans maliyeti olurdu. Bu, GitHub/GitLab gibi
platformların personal-access-token hash'leme modeliyle aynı yaklaşım.

Bu fazda registration KENDİ KENDİNE (self-service) — kullanıcıdan
önceden bir "enrollment secret" istenmiyor (bu, kullanıcıdan credential
talep etmeden ilerlemek için bilinçli bir kapsam kararı; registration
token/enrollment secret sertleştirmesi Faz 31 — Agent Security'nin
kapsamı, bkz. docs/roadmap.md)."""

import hashlib
import secrets

_TOKEN_BYTES = 32  # 256 bit


def generate_token() -> str:
    """Yeni, yüksek entropili bir agent bearer token'ı üretir."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_token(token: str) -> str:
    """Token'ın SHA-256 hex digest'i — DB'de saklanan tek biçim."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def extract_bearer_token(authorization_header: str | None) -> str | None:
    """`Authorization: Bearer <token>` header'ından token'ı çıkarır.
    Format yanlışsa `None` döner (çağıran taraf bunu `AgentAuthentication
    Error`'a çevirir) — asla ham header değerini loglamaz."""
    if not authorization_header:
        return None
    parts = authorization_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None
