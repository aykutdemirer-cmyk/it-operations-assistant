"""`app/routes/agent_ssh.py::agent_ssh_terminal` için testler — gerçek
bir WebSocket/DB bağlantısı kurulmaz (bkz. docs/decisions.md §11 —
`TestClient` bilinçli olarak kullanılmıyor); route fonksiyonu doğrudan
çağrılır, `service.get_agent_detail`/DB bağlantı fonksiyonları
mock'lanır."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.routes.agent_ssh import agent_ssh_terminal

pytestmark = pytest.mark.anyio


class FakeWebSocket:
    def __init__(self):
        self.sent = []
        self.accepted = False
        self.closed = False

    async def accept(self):
        self.accepted = True

    async def send_json(self, payload):
        self.sent.append(payload)

    async def close(self, *args, **kwargs):
        self.closed = True


async def test_rejects_when_agent_not_found():
    ws = FakeWebSocket()
    fake_conn = MagicMock()
    fake_conn.close = AsyncMock()

    with (
        patch("app.routes.agent_ssh.get_connection", AsyncMock(return_value=fake_conn)),
        patch("app.routes.agent_ssh.service.get_agent_detail", AsyncMock(return_value=None)),
    ):
        await agent_ssh_terminal(ws, uuid4())

    assert ws.accepted is True
    assert ws.sent[0]["type"] == "error"
    assert "bulunamadı" in ws.sent[0]["message"].lower()
    assert ws.closed is True


async def test_rejects_when_agent_has_no_local_ip():
    ws = FakeWebSocket()
    fake_conn = MagicMock()
    fake_conn.close = AsyncMock()
    fake_agent = MagicMock(local_ip=None)

    with (
        patch("app.routes.agent_ssh.get_connection", AsyncMock(return_value=fake_conn)),
        patch("app.routes.agent_ssh.service.get_agent_detail", AsyncMock(return_value=fake_agent)),
    ):
        await agent_ssh_terminal(ws, uuid4())

    assert ws.sent[0]["type"] == "error"
    assert "yerel ip" in ws.sent[0]["message"].lower()


async def test_delegates_to_ssh_proxy_with_agent_local_ip_never_client_supplied_host():
    """Kritik güvenlik testi: hedef host DAİMA agent kaydından gelir,
    istemciden ASLA alınmaz (bkz. `ssh_proxy.py` docstring'i)."""
    ws = FakeWebSocket()
    fake_conn = MagicMock()
    fake_conn.close = AsyncMock()
    fake_agent = MagicMock(local_ip="10.0.213.30")

    with (
        patch("app.routes.agent_ssh.get_connection", AsyncMock(return_value=fake_conn)),
        patch("app.routes.agent_ssh.service.get_agent_detail", AsyncMock(return_value=fake_agent)),
        patch("app.routes.agent_ssh.run_ssh_websocket_session", AsyncMock()) as mock_run,
    ):
        await agent_ssh_terminal(ws, uuid4())

    mock_run.assert_called_once_with(ws, host="10.0.213.30")


async def test_rejects_when_database_unreachable():
    ws = FakeWebSocket()

    with patch("app.routes.agent_ssh.get_connection", AsyncMock(side_effect=OSError("db down"))):
        await agent_ssh_terminal(ws, uuid4())

    assert ws.sent[0]["type"] == "error"
    assert ws.closed is True
