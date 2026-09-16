"""Faz 65/66 — Bilet olayları için asenkron SMTP e-posta bildirimi.

Yeni bir dış bağımlılık YOK — stdlib `smtplib`/`email`. SMTP çağrısı
event loop'u bloklamasın diye `asyncio.to_thread` içinde çalışır ve
tetik noktası `asyncio.create_task(...)` ile ateşle-unut kullanır:
bir e-posta hatası HİÇBİR ZAMAN bilet işlemini bozmaz, yalnızca
`logger.warning` üretir.

Faz 66 — yapılandırma çözümü: **önce DB (`smtp_config` satırı), yoksa
`.env`.** DB satırı `enabled=false` ise veya hiçbir yerde `server`
ayarlı değilse gönderim yapılmaz (opt-in).
"""

from __future__ import annotations

import asyncio
import html
import logging
import os
import smtplib
import ssl as ssl_module
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import Literal

SmtpEncryption = Literal["tls", "ssl", "none"]
_ENCRYPTIONS: tuple[SmtpEncryption, ...] = ("tls", "ssl", "none")

logger = logging.getLogger(__name__)

_SUBJECTS: dict[str, str] = {
    "new_ticket": "[{number}] Yeni Bilet Oluşturuldu",
    "new_reply": "[{number}] Biletinize Yeni Yanıt Eklendi",
    "resolved": "[{number}] Biletiniz Çözüldü Olarak İşaretlendi",
}
_HEADINGS: dict[str, str] = {
    "new_ticket": "Yeni bir destek bileti oluşturuldu",
    "new_reply": "Biletinize yeni bir yanıt eklendi",
    "resolved": "Biletiniz çözüldü olarak işaretlendi",
}


@dataclass
class SmtpConfig:
    enabled: bool
    server: str
    port: int
    encryption: SmtpEncryption
    username: str
    password: str
    from_email: str
    from_name: str
    it_group_email: str
    base_url: str

    @property
    def usable(self) -> bool:
        return bool(self.enabled and self.server)


def _int_or(default: int, raw: str | None) -> int:
    try:
        return int(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


def _normalize_encryption(raw: str | None) -> SmtpEncryption:
    value = (raw or "tls").strip().lower()
    return value if value in _ENCRYPTIONS else "tls"


def _from_env() -> SmtpConfig:
    server = os.environ.get("SMTP_SERVER", "").strip()
    username = os.environ.get("SMTP_USERNAME", "").strip()
    # Geriye dönük uyumluluk — Faz 65'in `SMTP_USE_TLS` bayrağı hâlâ
    # okunur (yalnızca `SMTP_ENCRYPTION` set edilmemişse): `true` → tls,
    # `false` → none. Yeni kurulumlar `SMTP_ENCRYPTION` kullanmalı.
    encryption_raw = os.environ.get("SMTP_ENCRYPTION")
    if encryption_raw is None and "SMTP_USE_TLS" in os.environ:
        encryption_raw = "tls" if _bool_env("SMTP_USE_TLS", True) else "none"
    return SmtpConfig(
        # `.env` tarafında ayrı bir "enabled" bayrağı yok — `SMTP_SERVER`
        # varsa açık sayılır (Faz 65 davranışı korunur).
        enabled=bool(server),
        server=server,
        port=_int_or(587, os.environ.get("SMTP_PORT")),
        encryption=_normalize_encryption(encryption_raw),
        username=username,
        password=os.environ.get("SMTP_PASSWORD", ""),
        from_email=os.environ.get("SMTP_FROM_EMAIL", "").strip() or (username or "no-reply@localhost"),
        from_name=os.environ.get("SMTP_FROM_NAME", "").strip() or "IT Operations Helpdesk",
        it_group_email=os.environ.get("SMTP_IT_GROUP_EMAIL", "").strip(),
        base_url=os.environ.get("TICKET_BASE_URL", "").strip().rstrip("/"),
    )


def _from_row(row) -> SmtpConfig:
    from app.pam.vault import decrypt_payload  # yerel import — döngüsel import riskini sıfırlar

    password = ""
    enc = row["encrypted_password"] or ""
    if enc:
        try:
            password = decrypt_payload(enc).get("password", "")
        except Exception as exc:  # noqa: BLE001
            logger.warning("SMTP parolası çözülemedi: %s", exc)
    username = (row["username"] or "").strip()
    return SmtpConfig(
        enabled=bool(row["enabled"]),
        server=(row["server"] or "").strip(),
        port=int(row["port"]),
        encryption=_normalize_encryption(row["encryption"]),
        username=username,
        password=password,
        from_email=(row["from_email"] or "").strip() or (username or "no-reply@localhost"),
        from_name=(row["from_name"] or "").strip() or "IT Operations Helpdesk",
        it_group_email=(row["it_group_email"] or "").strip(),
        base_url=(row["base_url"] or "").strip().rstrip("/"),
    )


async def load_config() -> SmtpConfig:
    """Önce `smtp_config` DB satırı, yoksa (veya DB erişilemezse) `.env`."""
    try:
        from app.db.smtp import get_config, get_connection

        conn = await get_connection()
        try:
            row = await get_config(conn)
        finally:
            await conn.close()
        if row is not None:
            return _from_row(row)
    except OSError:
        pass
    except Exception as exc:  # noqa: BLE001 — config çözümü asla akışı bozmamalı
        logger.warning("SMTP DB yapılandırması okunamadı, .env'e düşülüyor: %s", exc)
    return _from_env()


def _render_html(kind: str, *, number: str, title: str, creator: str, status: str | None, base_url: str) -> str:
    heading = _HEADINGS.get(kind, "Bilet güncellemesi")
    number = html.escape(number)
    title = html.escape(title)
    creator = html.escape(creator)
    status = html.escape(status) if status else None
    link_row = ""
    if base_url:
        url = f"{base_url}/tickets?ticket={number}"
        link_row = (
            f'<p style="margin:16px 0"><a href="{url}" '
            f'style="background:#1f6feb;color:#fff;padding:10px 18px;border-radius:6px;'
            f'text-decoration:none;display:inline-block">Bileti Görüntüle</a></p>'
        )
    status_row = (
        f'<tr><td style="padding:4px 12px 4px 0;color:#57606a">Durum</td><td><strong>{status}</strong></td></tr>'
        if status
        else ""
    )
    return (
        '<div style="font-family:Segoe UI,Arial,sans-serif;max-width:560px;margin:0 auto;'
        'border:1px solid #d0d7de;border-radius:10px;overflow:hidden">'
        '<div style="background:#0d1117;color:#fff;padding:16px 20px;font-size:15px;font-weight:600">'
        "IT Operations — Destek / Biletler</div>"
        '<div style="padding:20px">'
        f'<p style="margin:0 0 12px;font-size:15px">{heading}</p>'
        '<table style="border-collapse:collapse;font-size:14px;color:#1f2328">'
        f'<tr><td style="padding:4px 12px 4px 0;color:#57606a">Bilet No</td><td><strong>{number}</strong></td></tr>'
        f'<tr><td style="padding:4px 12px 4px 0;color:#57606a">Başlık</td><td>{title}</td></tr>'
        f'<tr><td style="padding:4px 12px 4px 0;color:#57606a">Oluşturan</td><td>{creator}</td></tr>'
        f"{status_row}"
        "</table>"
        f"{link_row}"
        '<p style="margin:16px 0 0;color:#8b949e;font-size:12px">Bu otomatik bir bildirimdir; yanıtlamayın.</p>'
        "</div></div>"
    )


def send_email_blocking(cfg: SmtpConfig, *, to: list[str], subject: str, body_html: str) -> None:
    """Senkron SMTP gönderimi — `asyncio.to_thread` içinden çağrılır.
    `test` endpoint'i de bunu kullanır (aynı yol GERÇEKTEN test edilsin).

    `encryption`: `"ssl"` → baştan itibaren şifreli bağlantı (`SMTP_SSL`,
    tipik port 465) — `"tls"` (STARTTLS, tipik port 587) ile KARIŞTIRILMAZ,
    ikisi farklı el sıkışmalar. `"none"` → düz metin (yalnızca izole/
    güvenilir bir ağda, ör. dahili relay, anlamlı)."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((cfg.from_name, cfg.from_email))
    msg["To"] = ", ".join(to)
    msg.set_content("Bu bildirimi görüntülemek için HTML destekli bir istemci kullanın.")
    msg.add_alternative(body_html, subtype="html")

    if cfg.encryption == "ssl":
        with smtplib.SMTP_SSL(cfg.server, cfg.port, timeout=15, context=ssl_module.create_default_context()) as smtp:
            if cfg.username:
                smtp.login(cfg.username, cfg.password)
            smtp.send_message(msg)
        return

    with smtplib.SMTP(cfg.server, cfg.port, timeout=15) as smtp:
        if cfg.encryption == "tls":
            smtp.starttls(context=ssl_module.create_default_context())
        if cfg.username:
            smtp.login(cfg.username, cfg.password)
        smtp.send_message(msg)


async def _deliver(
    kind: str, *, recipients: list[str] | None, number: str, title: str, creator: str, status: str | None
) -> None:
    cfg = await load_config()
    if not cfg.usable:
        return
    # `recipients=None` → "IT grup adresine gönder" (yeni bilet tetiği).
    raw = [cfg.it_group_email] if recipients is None else recipients
    to = [r for r in raw if r and "@" in r]
    if not to:
        return
    subject = _SUBJECTS[kind].format(number=number)
    body_html = _render_html(kind, number=number, title=title, creator=creator, status=status, base_url=cfg.base_url)
    try:
        await asyncio.to_thread(send_email_blocking, cfg, to=to, subject=subject, body_html=body_html)
        logger.info("Bilet e-postası gönderildi (%s → %s): %s", kind, ", ".join(to), number)
    except Exception as exc:  # noqa: BLE001 — e-posta hatası akışı bozmamalı
        logger.warning("Bilet e-postası gönderilemedi (%s, %s): %s", kind, number, exc)


def notify(
    kind: str,
    *,
    recipients: list[str] | None,
    number: str,
    title: str,
    creator: str,
    status: str | None = None,
) -> "asyncio.Task | None":
    """Ateşle-unut. Çağıran `await` ETMEZ. `recipients=None` → IT grup
    adresi. Yapılandırma çözümü (DB/`.env`) `_deliver` içinde asenkron
    yapılır — burada yalnızca `kind` doğrulanır ve bir task planlanır.
    Oluşturulan `Task` döner (yalnızca testlerin beklemesi için)."""
    try:
        if kind not in _SUBJECTS:
            return None
        loop = asyncio.get_running_loop()
        return loop.create_task(
            _deliver(kind, recipients=recipients, number=number, title=title, creator=creator, status=status)
        )
    except RuntimeError:
        return None
    except Exception as exc:  # noqa: BLE001 — e-posta planlaması akışı bozmamalı
        logger.warning("Bilet e-postası planlanamadı (%s, %s): %s", kind, number, exc)
        return None
