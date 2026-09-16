"""Faz 66 — `/api/settings/smtp`: bilet e-posta bildirimi (SMTP)
yapılandırması. Yetki `require_role("ADMIN")` — bilet taksonomisi
yönetimiyle AYNI sınır (SMTP bir PAM kavramı değil). Parola
`vault_credentials`/`ldap_config` ile AYNI Fernet anahtarıyla
şifrelenir."""

import asyncio
import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.dependencies import require_role
from app.db.smtp import get_config, get_connection, record_test_result, upsert_config
from app.pam.vault import decrypt_payload, encrypt_payload
from app.services import email_service

router = APIRouter(prefix="/api/settings/smtp", tags=["smtp"], dependencies=[Depends(require_role("ADMIN"))])

logger = logging.getLogger(__name__)

SmtpEncryption = Literal["tls", "ssl", "none"]


class SmtpConfigRequest(BaseModel):
    enabled: bool = True
    server: str = Field(min_length=1, max_length=255)
    port: int = Field(default=587, ge=1, le=65535)
    encryption: SmtpEncryption = "tls"
    username: str = Field(default="", max_length=255)
    # `None`/boş → mevcut parolayı KORU (LDAP bind parolası deseniyle aynı).
    password: str | None = Field(default=None, max_length=255)
    from_email: str = Field(min_length=3, max_length=320)
    from_name: str = Field(default="IT Operations Helpdesk", max_length=255)
    it_group_email: str = Field(default="", max_length=320)
    base_url: str = Field(default="", max_length=500)


class SmtpConfigResponse(BaseModel):
    enabled: bool
    server: str
    port: int
    encryption: SmtpEncryption
    username: str
    # Parola ASLA düz metin dönmez — yalnızca ayarlı olup olmadığı.
    password_set: bool
    from_email: str
    from_name: str
    it_group_email: str
    base_url: str
    last_test_status: str | None
    last_test_error: str | None
    last_test_at: object | None
    updated_at: object


class SmtpTestRequest(BaseModel):
    # Boş → kayıtlı IT grup adresine gönder.
    to: str = Field(default="", max_length=320)


class SmtpTestResult(BaseModel):
    success: bool
    message: str


def _to_response(row) -> SmtpConfigResponse:
    return SmtpConfigResponse(
        enabled=row["enabled"],
        server=row["server"],
        port=row["port"],
        encryption=row["encryption"],
        username=row["username"],
        password_set=bool(row["encrypted_password"]),
        from_email=row["from_email"],
        from_name=row["from_name"],
        it_group_email=row["it_group_email"],
        base_url=row["base_url"],
        last_test_status=row["last_test_status"],
        last_test_error=row["last_test_error"],
        last_test_at=row["last_test_at"],
        updated_at=row["updated_at"],
    )


async def _connect():
    try:
        return await get_connection()
    except OSError as exc:
        logger.warning("PostgreSQL erişilemedi (smtp settings)")
        raise HTTPException(status_code=503, detail={"database": "unreachable"}) from exc


async def _resolve_encrypted_password(conn, payload: SmtpConfigRequest) -> str:
    """Parola doluysa şifreler; boş/None ise KAYITLI şifreli değeri
    bayt düzeyinde korur (yeni kayıtta parola opsiyonel — kimlik
    doğrulamasız relay için)."""
    if payload.password:
        return encrypt_payload({"password": payload.password})
    existing = await get_config(conn)
    return existing["encrypted_password"] if existing is not None else ""


@router.get("", response_model=SmtpConfigResponse | None)
async def get_smtp_config_route() -> SmtpConfigResponse | None:
    conn = await _connect()
    try:
        row = await get_config(conn)
    finally:
        await conn.close()
    return _to_response(row) if row is not None else None


@router.put("", response_model=SmtpConfigResponse)
async def update_smtp_config_route(payload: SmtpConfigRequest) -> SmtpConfigResponse:
    conn = await _connect()
    try:
        encrypted_password = await _resolve_encrypted_password(conn, payload)
        row = await upsert_config(
            conn,
            enabled=payload.enabled,
            server=payload.server.strip(),
            port=payload.port,
            encryption=payload.encryption,
            username=payload.username.strip(),
            encrypted_password=encrypted_password,
            from_email=payload.from_email.strip(),
            from_name=payload.from_name.strip() or "IT Operations Helpdesk",
            it_group_email=payload.it_group_email.strip(),
            base_url=payload.base_url.strip().rstrip("/"),
        )
    finally:
        await conn.close()
    return _to_response(row)


@router.post("/test", response_model=SmtpTestResult)
async def test_smtp_route(payload: SmtpTestRequest) -> SmtpTestResult:
    """KAYITLI yapılandırmayla GERÇEK bir test e-postası gönderir.
    Başarısızlıkta 4xx/5xx DEĞİL `success=false` döner (LDAP/SNMP
    "Test Connection" ilkesi)."""
    conn = await _connect()
    try:
        row = await get_config(conn)
        if row is None:
            return SmtpTestResult(success=False, message="Önce SMTP yapılandırması kaydedilmeli")
        cfg = email_service.SmtpConfig(
            enabled=True,
            server=row["server"],
            port=row["port"],
            encryption=row["encryption"],
            username=row["username"],
            password=decrypt_payload(row["encrypted_password"]).get("password", "") if row["encrypted_password"] else "",
            from_email=row["from_email"],
            from_name=row["from_name"],
            it_group_email=row["it_group_email"],
            base_url=row["base_url"],
        )
        target = payload.to.strip() or cfg.it_group_email
        if not target or "@" not in target:
            return SmtpTestResult(success=False, message="Geçerli bir hedef adres veya kayıtlı IT grup adresi gerekli")

        try:
            await asyncio.to_thread(
                email_service.send_email_blocking,
                cfg,
                to=[target],
                subject="[IT Operations] SMTP Test E-Postası",
                body_html="<p>Bu bir test e-postasıdır. SMTP yapılandırması çalışıyor.</p>",
            )
        except Exception as exc:  # noqa: BLE001
            await record_test_result(conn, status="error", error=str(exc))
            return SmtpTestResult(success=False, message=str(exc))

        await record_test_result(conn, status="success", error=None)
        return SmtpTestResult(success=True, message=f"Test e-postası {target} adresine gönderildi")
    finally:
        await conn.close()
