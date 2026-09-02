"""`agent/client.py` testleri — gerçek ağ isteği YOK, `urllib.request.
urlopen` mock'lanır."""

import io
import json
import urllib.error
from unittest.mock import patch

import pytest

from agent.client import (
    BackendAuthenticationError,
    BackendClient,
    BackendServerError,
    BackendUnavailableError,
    BackendValidationError,
)


class _FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = json.dumps(body).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_register_returns_parsed_json():
    client = BackendClient("http://backend:8000")
    with patch("urllib.request.urlopen", return_value=_FakeResponse(201, {"agent_id": "a1", "token": "t1"})):
        result = client.register({"hostname": "host1", "os": "linux", "agent_version": "1.0.0"})
    assert result == {"agent_id": "a1", "token": "t1"}


def test_connection_error_raises_backend_unavailable():
    client = BackendClient("http://backend:8000")
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("connection refused")):
        with pytest.raises(BackendUnavailableError):
            client.register({"hostname": "h", "os": "linux", "agent_version": "1.0.0"})


def test_401_raises_backend_authentication_error():
    client = BackendClient("http://backend:8000")
    error = urllib.error.HTTPError(
        "http://backend:8000/api/agents/heartbeat", 401, "Unauthorized", {},
        io.BytesIO(json.dumps({"detail": "Kimlik doğrulama başarısız"}).encode()),
    )
    with patch("urllib.request.urlopen", side_effect=error):
        with pytest.raises(BackendAuthenticationError):
            client.heartbeat("bad-token", {"agent_version": "1.0.0"})


def test_422_raises_backend_validation_error():
    client = BackendClient("http://backend:8000")
    error = urllib.error.HTTPError(
        "http://backend:8000/api/agents/register", 422, "Unprocessable", {},
        io.BytesIO(json.dumps({"detail": "geçersiz payload"}).encode()),
    )
    with patch("urllib.request.urlopen", side_effect=error):
        with pytest.raises(BackendValidationError):
            client.register({})


def test_500_raises_backend_server_error():
    client = BackendClient("http://backend:8000")
    error = urllib.error.HTTPError(
        "http://backend:8000/api/health", 500, "Internal Server Error", {}, io.BytesIO(b"{}"),
    )
    with patch("urllib.request.urlopen", side_effect=error):
        with pytest.raises(BackendServerError):
            client.test_connection()


def test_send_telemetry_includes_bearer_header():
    client = BackendClient("http://backend:8000")
    captured = {}

    def _fake_urlopen(request, timeout=None, context=None):
        captured["headers"] = dict(request.header_items())
        return _FakeResponse(200, {})

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        client.send_telemetry("secret-token", "agent-1", {"collected_at": "2026-01-01T00:00:00Z"})

    assert captured["headers"]["Authorization"] == "Bearer secret-token"


def test_verify_tls_false_disables_certificate_checks():
    client = BackendClient("http://backend:8000", verify_tls=False)
    assert client._ssl_context is not None
    assert client._ssl_context.verify_mode.name == "CERT_NONE"


def test_verify_tls_true_uses_default_ssl_behavior():
    client = BackendClient("http://backend:8000", verify_tls=True)
    assert client._ssl_context is None


# --- Faz 33: get_pending_commands / report_command_result ---


def test_get_pending_commands_returns_command_list():
    client = BackendClient("http://backend:8000")
    body = {"commands": [{"id": "c1", "command_type": "kill_process", "action": "kill", "target": "1234"}]}
    with patch("urllib.request.urlopen", return_value=_FakeResponse(200, body)):
        result = client.get_pending_commands("token-1", "agent-1")
    assert result == body["commands"]


def test_get_pending_commands_defaults_to_empty_list_when_missing_key():
    client = BackendClient("http://backend:8000")
    with patch("urllib.request.urlopen", return_value=_FakeResponse(200, {})):
        result = client.get_pending_commands("token-1", "agent-1")
    assert result == []


def test_get_pending_commands_uses_bearer_header_and_correct_path():
    client = BackendClient("http://backend:8000")
    captured = {}

    def _fake_urlopen(request, timeout=None, context=None):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        return _FakeResponse(200, {"commands": []})

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        client.get_pending_commands("secret-token", "agent-1")

    assert captured["url"] == "http://backend:8000/api/agents/agent-1/commands/pending"
    assert captured["headers"]["Authorization"] == "Bearer secret-token"


def test_report_command_result_posts_status_and_detail():
    client = BackendClient("http://backend:8000")
    captured = {}

    def _fake_urlopen(request, timeout=None, context=None):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(200, {"status": "ok"})

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        client.report_command_result("secret-token", "agent-1", "cmd-1", "succeeded", "PID 1234 sonlandırıldı")

    assert captured["url"] == "http://backend:8000/api/agents/agent-1/commands/cmd-1/result"
    assert captured["body"] == {"status": "succeeded", "result_detail": "PID 1234 sonlandırıldı"}
