"""Faz 66 — `/api/settings/smtp`. Gerçek PostgreSQL'e bağlı (isolated_db)
+ mock'lu `smtplib.SMTP`."""

from unittest.mock import patch

import pytest

from app.auth.permissions import default_permissions_for_role
from app.auth.security import hash_password
from app.db.users import insert_user, set_permissions

pytestmark = pytest.mark.anyio


async def _headers(client, isolated_db, *, username, role) -> dict:
    row = await insert_user(
        isolated_db, username=username, password_hash=hash_password("s3cret-pw!"), role=role, full_name=None
    )
    await set_permissions(isolated_db, row["id"], default_permissions_for_role(role))
    resp = await client.post("/api/auth/login", json={"username": username, "password": "s3cret-pw!"})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


_VALID = {
    "server": "smtp.sirket.local",
    "port": 587,
    "encryption": "tls",
    "username": "bildirim@sirket.local",
    "password": "gizli-parola",
    "from_email": "bildirim@sirket.local",
    "from_name": "IT Operations Helpdesk",
    "it_group_email": "it@sirket.local",
    "base_url": "https://itops.sirket.local/",
}


async def test_get_returns_null_when_unconfigured(isolated_db, client):
    admin = await _headers(client, isolated_db, username="smtp-admin", role="ADMIN")
    resp = await client.get("/api/settings/smtp", headers=admin)
    assert resp.status_code == 200
    assert resp.json() is None


async def test_put_saves_and_masks_password(isolated_db, client):
    admin = await _headers(client, isolated_db, username="smtp-admin2", role="ADMIN")
    resp = await client.put("/api/settings/smtp", headers=admin, json=_VALID)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["server"] == "smtp.sirket.local"
    assert body["base_url"] == "https://itops.sirket.local"  # trailing slash stripped
    assert body["password_set"] is True
    assert "password" not in body  # düz metin ASLA dönmez

    got = (await client.get("/api/settings/smtp", headers=admin)).json()
    assert got["username"] == "bildirim@sirket.local" and got["password_set"] is True


async def test_put_without_password_preserves_existing(isolated_db, client):
    admin = await _headers(client, isolated_db, username="smtp-admin3", role="ADMIN")
    await client.put("/api/settings/smtp", headers=admin, json=_VALID)

    no_pw = {**_VALID, "port": 2525}
    no_pw.pop("password")
    resp = await client.put("/api/settings/smtp", headers=admin, json=no_pw)
    assert resp.status_code == 200
    assert resp.json()["port"] == 2525
    assert resp.json()["password_set"] is True  # korundu


async def test_non_admin_forbidden(isolated_db, client):
    op = await _headers(client, isolated_db, username="smtp-op", role="OPERATOR")
    assert (await client.get("/api/settings/smtp", headers=op)).status_code == 403
    assert (await client.put("/api/settings/smtp", headers=op, json=_VALID)).status_code == 403


async def test_test_endpoint_sends_via_smtplib(isolated_db, client):
    admin = await _headers(client, isolated_db, username="smtp-admin4", role="ADMIN")
    await client.put("/api/settings/smtp", headers=admin, json=_VALID)

    sent = []

    class _FakeSMTP:
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
            sent.append(msg)

    with patch("smtplib.SMTP", _FakeSMTP):
        resp = await client.post("/api/settings/smtp/test", headers=admin, json={"to": "ben@sirket.local"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert len(sent) == 1 and sent[0]["To"] == "ben@sirket.local"
    assert "IT Operations Helpdesk" in sent[0]["From"]

    status = (await client.get("/api/settings/smtp", headers=admin)).json()
    assert status["last_test_status"] == "success"


async def test_test_endpoint_uses_smtp_ssl_for_ssl_encryption(isolated_db, client):
    admin = await _headers(client, isolated_db, username="smtp-admin4b", role="ADMIN")
    await client.put("/api/settings/smtp", headers=admin, json={**_VALID, "port": 465, "encryption": "ssl"})

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

    with patch("smtplib.SMTP_SSL", _FakeSmtpSsl), patch("smtplib.SMTP") as smtp_plain:
        resp = await client.post("/api/settings/smtp/test", headers=admin, json={"to": "ben@sirket.local"})
    assert resp.status_code == 200 and resp.json()["success"] is True
    assert len(sent) == 1
    smtp_plain.assert_not_called()  # SSL yolunda düz `SMTP` HİÇ kullanılmaz


async def test_test_endpoint_reports_failure_without_raising(isolated_db, client):
    admin = await _headers(client, isolated_db, username="smtp-admin5", role="ADMIN")
    await client.put("/api/settings/smtp", headers=admin, json=_VALID)

    class _BrokenSMTP:
        def __init__(self, *a, **kw):
            raise OSError("connection refused")

    with patch("smtplib.SMTP", _BrokenSMTP):
        resp = await client.post("/api/settings/smtp/test", headers=admin, json={"to": "ben@sirket.local"})
    assert resp.status_code == 200
    assert resp.json()["success"] is False
    assert "connection refused" in resp.json()["message"]
