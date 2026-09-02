"""`app/agents/ssh_proxy.py` için testler — GERÇEK bir SSH bağlantısı
ASLA kurulmaz, `asyncssh.connect`/`FastAPI.WebSocket` tamamen mock'lanır.
Odak: kimlik bilgisi asla loglanmaz, hata mesajları dürüst, WS mesaj
protokolü doğru."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import asyncssh
import pytest

from app.agents.ssh_proxy import run_ssh_websocket_session

pytestmark = pytest.mark.anyio


class FakeWebSocketDisconnect(Exception):
    pass


class FakeWebSocket:
    """`fastapi.WebSocket`'in test double'ı — `accept`/`send_json`/
    `receive_json`/`close` çağrılarını kaydeder, gerçek bir soket AÇMAZ."""

    def __init__(self, incoming: list[dict]):
        self._incoming = list(incoming)
        self.sent: list[dict] = []
        self.accepted = False
        self.closed = False

    async def accept(self):
        self.accepted = True

    async def send_json(self, payload):
        self.sent.append(payload)

    async def receive_json(self):
        if not self._incoming:
            # Reader task'ın (arka planda stdout'u WS'e aktaran) en
            # azından bir zamanlayıcı turu almasını garanti eder —
            # aksi halde bu coroutine hiç askıya alınmadan tamamlanıp
            # reader task'a hiç fırsat vermeden `WebSocketDisconnect`
            # fırlatabilir (gerçek asyncio zamanlama ayrıntısı, gerçek
            # kullanımda sorun değil — istemci bağlantıyı GERÇEKTEN açık
            # tutar).
            await asyncio.sleep(0.05)
            from fastapi import WebSocketDisconnect

            raise WebSocketDisconnect()
        return self._incoming.pop(0)

    async def close(self):
        self.closed = True


def _fake_process(stdout_chunks: list[str]):
    process = MagicMock()
    stdout = AsyncMock()
    stdout.read = AsyncMock(side_effect=[*stdout_chunks, ""])
    process.stdout = stdout
    process.stdin = MagicMock()
    return process


async def test_rejects_when_first_message_is_not_connect():
    ws = FakeWebSocket(incoming=[{"type": "input", "data": "ls\n"}])
    await run_ssh_websocket_session(ws, host="10.0.213.30")

    assert ws.accepted is True
    assert ws.sent[0]["type"] == "error"
    assert ws.closed is True


async def test_rejects_when_username_missing():
    ws = FakeWebSocket(incoming=[{"type": "connect", "password": "x"}])
    await run_ssh_websocket_session(ws, host="10.0.213.30")

    assert ws.sent[0]["type"] == "error"
    assert "kullanıcı" in ws.sent[0]["message"].lower()


async def test_reports_authentication_failure_honestly():
    ws = FakeWebSocket(incoming=[{"type": "connect", "username": "bob", "password": "wrong"}])

    with patch("app.agents.ssh_proxy.asyncssh.connect", side_effect=asyncssh.PermissionDenied("denied")):
        await run_ssh_websocket_session(ws, host="10.0.213.30")

    assert ws.sent[0] == {"type": "error", "message": "Kimlik doğrulama başarısız"}
    # Şifre hiçbir gönderilen mesajda GEÇMEMELİ.
    assert all("wrong" not in str(m) for m in ws.sent)


async def test_reports_unreachable_host_honestly():
    ws = FakeWebSocket(incoming=[{"type": "connect", "username": "bob", "password": "x"}])

    with patch("app.agents.ssh_proxy.asyncssh.connect", side_effect=OSError("connection refused")):
        await run_ssh_websocket_session(ws, host="10.0.213.99")

    assert ws.sent[0]["type"] == "error"
    assert "bağlan" in ws.sent[0]["message"].lower()


async def test_successful_session_relays_output_and_sends_connected():
    ws = FakeWebSocket(
        incoming=[
            {"type": "connect", "username": "bob", "password": "x", "cols": 80, "rows": 24},
        ]
    )
    fake_conn = MagicMock()
    process = _fake_process(["hello ", "world"])
    fake_conn.create_process = AsyncMock(return_value=process)

    with patch("app.agents.ssh_proxy.asyncssh.connect", AsyncMock(return_value=fake_conn)):
        await run_ssh_websocket_session(ws, host="10.0.213.30")

    assert {"type": "connected"} in ws.sent
    data_chunks = [m["data"] for m in ws.sent if m.get("type") == "data"]
    assert data_chunks == ["hello ", "world"]
    fake_conn.close.assert_called_once()


async def test_input_message_is_written_to_ssh_stdin():
    ws = FakeWebSocket(
        incoming=[
            {"type": "connect", "username": "bob", "password": "x"},
            {"type": "input", "data": "ls\n"},
        ]
    )
    fake_conn = MagicMock()
    process = _fake_process([])
    fake_conn.create_process = AsyncMock(return_value=process)

    with patch("app.agents.ssh_proxy.asyncssh.connect", AsyncMock(return_value=fake_conn)):
        await run_ssh_websocket_session(ws, host="10.0.213.30")

    process.stdin.write.assert_any_call("ls\n")


async def test_resize_message_calls_change_terminal_size():
    ws = FakeWebSocket(
        incoming=[
            {"type": "connect", "username": "bob", "password": "x"},
            {"type": "resize", "cols": 120, "rows": 40},
        ]
    )
    fake_conn = MagicMock()
    process = _fake_process([])
    fake_conn.create_process = AsyncMock(return_value=process)

    with patch("app.agents.ssh_proxy.asyncssh.connect", AsyncMock(return_value=fake_conn)):
        await run_ssh_websocket_session(ws, host="10.0.213.30")

    process.change_terminal_size.assert_called_once_with(120, 40)


async def test_never_logs_password(caplog):
    ws = FakeWebSocket(incoming=[{"type": "connect", "username": "bob", "password": "super-secret-pw"}])

    with patch("app.agents.ssh_proxy.asyncssh.connect", side_effect=asyncssh.PermissionDenied("denied")):
        with caplog.at_level("DEBUG"):
            await run_ssh_websocket_session(ws, host="10.0.213.30")

    assert "super-secret-pw" not in caplog.text
