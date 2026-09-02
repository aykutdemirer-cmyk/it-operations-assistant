"""Enrollment code üretimi/doğrulanması (Faz 31).

Self-service registration'ın (Faz 28) bilinen güvenlik açığını kapatır:
artık `POST /api/agents/register` GEÇERLİ, süresi dolmamış, daha önce
kullanılmamış bir kod ister. Kod bir credential/secret DEĞİLDİR (tek
başına hiçbir kaynağa erişim vermez) — insan-okur, kısa ömürlü,
tek kullanımlık bir "bu kaydı ben başlattım" onayıdır. Gerçek yetkilendirme
hâlâ agent'ın kendi bearer token'ında (Faz 28) yaşar."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import asyncpg

from app.agents.exceptions import (
    EnrollmentCodeAlreadyUsedError,
    EnrollmentCodeExpiredError,
    EnrollmentCodeInvalidError,
)
from app.db import agent_enrollment as enrollment_repo

# Karışabilecek karakterler (0/O, 1/I/L) KASITLI olarak alfabede yok —
# kullanıcı kodu elle bir Agent kurulum ekranına yazacak.
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_GROUP_LENGTH = 3
_GROUP_COUNT = 3
_DEFAULT_TTL_MINUTES = 10


def _generate_code() -> str:
    groups = [
        "".join(secrets.choice(_ALPHABET) for _ in range(_GROUP_LENGTH)) for _ in range(_GROUP_COUNT)
    ]
    return "-".join(groups)


def _normalize(code: str) -> str:
    """Kullanıcı elle girerken küçük harf/fazla boşluk kullanabilir —
    karşılaştırma öncesi normalize edilir. Depolama her zaman büyük
    harf (bkz. `_generate_code`)."""
    return code.strip().upper()


async def create_enrollment_code(
    conn: asyncpg.Connection, ttl_minutes: int = _DEFAULT_TTL_MINUTES
) -> dict:
    code = _generate_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    return await enrollment_repo.insert_code(conn, code=code, expires_at=expires_at)


async def list_active_enrollment_codes(conn: asyncpg.Connection) -> list[dict]:
    return await enrollment_repo.list_active_codes(conn)


async def consume_enrollment_code(conn: asyncpg.Connection, code: str) -> str:
    """Kodu doğrular ve ATOMİK olarak tüketir — geçersizse/süresi
    dolmuşsa/zaten kullanılmışsa spesifik bir hata fırlatır (çağıran
    taraf, `register_agent`, bunu 401/403'e çevirir). Başarılı olursa
    normalize edilmiş kodu döner (`register_agent` bunu agent
    oluşturulduktan SONRA `link_code_to_agent` ile ilişkilendirir —
    bkz. `app/db/agent_enrollment.py::consume_code` docstring'i, sıra
    ÖNEMLİ)."""
    normalized = _normalize(code)
    row = await enrollment_repo.get_code(conn, normalized)
    if row is None:
        raise EnrollmentCodeInvalidError("Enrollment code bulunamadı")
    if row["used_at"] is not None:
        raise EnrollmentCodeAlreadyUsedError("Enrollment code daha önce kullanılmış")
    if row["expires_at"] < datetime.now(timezone.utc):
        raise EnrollmentCodeExpiredError("Enrollment code süresi dolmuş")

    consumed = await enrollment_repo.consume_code(conn, normalized)
    if consumed is None:
        # Yukarıdaki kontrollerden SONRA, ama gerçek UPDATE'ten ÖNCE
        # başka bir istek aynı kodu tüketmiş olabilir (race condition) —
        # `consume_code`'un atomik `WHERE used_at IS NULL` koşulu bunu
        # yakalar, burada aynı hatayı fırlatırız.
        raise EnrollmentCodeAlreadyUsedError("Enrollment code daha önce kullanılmış")
    return normalized
