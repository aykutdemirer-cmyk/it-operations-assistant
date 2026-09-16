"""Faz 65/66 — `app/services/email_service.py`. Gerçek SMTP sunucusuna
bağlanmadan (mock'lu `smtplib.SMTP`) tetiklerin doğru alıcı/konu/gövde
ürettiğini, config eksik/SMTP hatalı durumların akışı BOZMADIĞINI ve
Faz 66'nın DB-öncelikli config çözümünü doğrular."""

import asyncio
from unittest.mock import patch

import pytest

from app.services import email_service
from app.services.email_service import SmtpConfig

pytestmark = pytest.mark.anyio


class _FakeSMTP:
    sent: list = []
    raise_on_send = False

    def __init__(self, *a, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, *a, **kw):
        pass

    def login(self, *a):
        pass

    def send_message(self, msg):
        if _FakeSMTP.raise_on_send:
            raise OSError("SMTP down")
        _FakeSMTP.sent.append(msg)


@pytest.fixture(autouse=True)
def _reset():
    _FakeSMTP.sent = []
    _FakeSMTP.raise_on_send = False
    yield


def _cfg(**over) -> SmtpConfig:
    base = dict(
        enabled=True,
        server="smtp.test.local",
        port=587,
        encryption="none",
        username="",
        password="",
        from_email="noreply@test.local",
        from_name="IT Test Helpdesk",
        it_group_email="it-group@test.local",
        base_url="https://itops.test.local",
    )
    base.update(over)
    return SmtpConfig(**base)


async def _run_notify(cfg: SmtpConfig | None, **kw):
    async def _load():
        return cfg if cfg is not None else _cfg(enabled=False, server="")

    with patch("smtplib.SMTP", _FakeSMTP), patch.object(email_service, "load_config", _load):
        task = email_service.notify(**kw)
        if task is not None:
            await asyncio.gather(task, return_exceptions=True)


async def test_noop_when_config_unusable():
    await _run_notify(
        _cfg(enabled=False),
        kind="new_reply",
        recipients=["u@x.com"],
        number="INC-2026-0001",
        title="x",
        creator="op",
    )
    assert _FakeSMTP.sent == []


async def test_new_ticket_goes_to_it_group_when_recipients_none():
    await _run_notify(
        _cfg(),
        kind="new_ticket",
        recipients=None,
        number="INC-2026-0007",
        title="Switch down",
        creator="operator1",
    )
    assert len(_FakeSMTP.sent) == 1
    msg = _FakeSMTP.sent[0]
    assert msg["To"] == "it-group@test.local"
    assert "IT Test Helpdesk" in msg["From"]
    assert "INC-2026-0007" in msg["Subject"] and "Yeni Bilet" in msg["Subject"]
    body = msg.get_body(preferencelist=("html",)).get_content()
    assert "INC-2026-0007" in body and "Switch down" in body and "operator1" in body
    assert "https://itops.test.local/tickets?ticket=INC-2026-0007" in body


def test_send_email_blocking_uses_smtp_ssl_for_ssl_encryption():
    sent = []

    class _FakeSmtpSsl:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def login(self, *a):
            pass

        def send_message(self, msg):
            sent.append(msg)

    cfg = _cfg(encryption="ssl", port=465)
    with patch("smtplib.SMTP_SSL", _FakeSmtpSsl), patch("smtplib.SMTP") as smtp_plain:
        email_service.send_email_blocking(cfg, to=["x@test.local"], subject="s", body_html="<p>x</p>")
    assert len(sent) == 1
    smtp_plain.assert_not_called()


def test_send_email_blocking_skips_starttls_for_none_encryption():
    with patch("smtplib.SMTP", _FakeSMTP):
        email_service.send_email_blocking(
            _cfg(encryption="none"), to=["x@test.local"], subject="s", body_html="<p>x</p>"
        )
    assert len(_FakeSMTP.sent) == 1


async def test_reply_and_resolved_subjects():
    await _run_notify(
        _cfg(), kind="new_reply", recipients=["owner@test.local"], number="INC-1", title="t", creator="c"
    )
    await _run_notify(
        _cfg(),
        kind="resolved",
        recipients=["owner@test.local"],
        number="INC-1",
        title="t",
        creator="c",
        status="RESOLVED",
    )
    subjects = [m["Subject"] for m in _FakeSMTP.sent]
    assert any("Yeni Yanıt" in s for s in subjects)
    assert any("Çözüldü" in s for s in subjects)


async def test_invalid_recipients_are_filtered():
    await _run_notify(
        _cfg(), kind="new_reply", recipients=["", None, "not-an-email"], number="INC-1", title="t", creator="c"
    )
    assert _FakeSMTP.sent == []


async def test_smtp_exception_is_swallowed():
    _FakeSMTP.raise_on_send = True
    await _run_notify(
        _cfg(), kind="new_reply", recipients=["owner@test.local"], number="INC-1", title="t", creator="c"
    )
    assert _FakeSMTP.sent == []


async def test_it_group_none_recipients_with_empty_group_sends_nothing():
    await _run_notify(
        _cfg(it_group_email=""),
        kind="new_ticket",
        recipients=None,
        number="INC-9",
        title="t",
        creator="c",
    )
    assert _FakeSMTP.sent == []


# ---- Faz 66 — DB-öncelikli config çözümü (`load_config`) -------------


async def test_load_config_prefers_db_row_over_env(monkeypatch):
    monkeypatch.setenv("SMTP_SERVER", "env-server.local")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "env@x.local")

    row = {
        "enabled": True,
        "server": "db-server.local",
        "port": 2525,
        "encryption": "ssl",
        "username": "dbuser",
        "encrypted_password": "",
        "from_email": "db@x.local",
        "from_name": "DB Helpdesk",
        "it_group_email": "db-it@x.local",
        "base_url": "https://db.local/",
    }

    class _Conn:
        async def close(self):
            pass

    async def _get_conn():
        return _Conn()

    async def _get_config(_conn):
        return row

    with patch("app.db.smtp.get_connection", _get_conn), patch("app.db.smtp.get_config", _get_config):
        cfg = await email_service.load_config()
    assert cfg.server == "db-server.local"
    assert cfg.port == 2525
    assert cfg.encryption == "ssl"
    assert cfg.from_email == "db@x.local"
    assert cfg.from_name == "DB Helpdesk"
    assert cfg.base_url == "https://db.local"  # trailing slash stripped


async def test_load_config_falls_back_to_env_when_no_db_row(monkeypatch):
    monkeypatch.setenv("SMTP_SERVER", "env-server.local")
    monkeypatch.setenv("SMTP_FROM_EMAIL", "env@x.local")

    class _Conn:
        async def close(self):
            pass

    async def _get_conn():
        return _Conn()

    async def _get_config(_conn):
        return None

    with patch("app.db.smtp.get_connection", _get_conn), patch("app.db.smtp.get_config", _get_config):
        cfg = await email_service.load_config()
    assert cfg.server == "env-server.local"
    assert cfg.from_email == "env@x.local"


async def test_load_config_db_disabled_row_is_not_usable(monkeypatch):
    monkeypatch.delenv("SMTP_SERVER", raising=False)
    row = {
        "enabled": False,
        "server": "db-server.local",
        "port": 587,
        "encryption": "tls",
        "username": "",
        "encrypted_password": "",
        "from_email": "db@x.local",
        "from_name": "",
        "it_group_email": "",
        "base_url": "",
    }

    class _Conn:
        async def close(self):
            pass

    with patch("app.db.smtp.get_connection", lambda: _mk(_Conn())), patch("app.db.smtp.get_config", lambda _c: _mk(row)):
        cfg = await email_service.load_config()
    assert cfg.usable is False


def _mk(value):
    async def _coro():
        return value

    return _coro()
