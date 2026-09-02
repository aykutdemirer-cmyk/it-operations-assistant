from pathlib import Path

import pytest

from agent.config import ConfigError, load_config


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in (
        "BACKEND_URL", "AGENT_ID", "AGENT_TOKEN", "HEARTBEAT_INTERVAL",
        "TELEMETRY_INTERVAL", "INVENTORY_INTERVAL", "VERIFY_TLS",
        "AGENT_STATE_FILE", "MAX_PROCESSES_REPORTED",
    ):
        monkeypatch.delenv(key, raising=False)


def test_load_config_requires_backend_url(tmp_path):
    with pytest.raises(ConfigError):
        load_config(dotenv_path=tmp_path / "nonexistent.env")


def test_load_config_reads_backend_url(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKEND_URL", "http://10.0.0.5:8000/")
    config = load_config(dotenv_path=tmp_path / "nonexistent.env")
    assert config.backend_url == "http://10.0.0.5:8000"  # trailing slash kırpılır


def test_load_config_uses_safe_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKEND_URL", "http://backend:8000")
    config = load_config(dotenv_path=tmp_path / "nonexistent.env")

    assert config.heartbeat_interval == 30
    assert config.telemetry_interval == 30
    assert config.inventory_interval == 300
    assert config.verify_tls is True
    assert config.agent_id is None
    assert config.agent_token is None


def test_load_config_reads_agent_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKEND_URL", "http://backend:8000")
    monkeypatch.setenv("AGENT_ID", "abc-123")
    monkeypatch.setenv("AGENT_TOKEN", "secret-token-value")
    config = load_config(dotenv_path=tmp_path / "nonexistent.env")

    assert config.agent_id == "abc-123"
    assert config.agent_token == "secret-token-value"


def test_load_config_verify_tls_false(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKEND_URL", "http://backend:8000")
    monkeypatch.setenv("VERIFY_TLS", "false")
    config = load_config(dotenv_path=tmp_path / "nonexistent.env")
    assert config.verify_tls is False


def test_load_config_invalid_interval_falls_back_to_default(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKEND_URL", "http://backend:8000")
    monkeypatch.setenv("HEARTBEAT_INTERVAL", "not-a-number")
    config = load_config(dotenv_path=tmp_path / "nonexistent.env")
    assert config.heartbeat_interval == 30


def test_load_config_reads_dotenv_file(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("BACKEND_URL=http://from-dotenv:8000\nHEARTBEAT_INTERVAL=15\n", encoding="utf-8")

    config = load_config(dotenv_path=env_file)

    assert config.backend_url == "http://from-dotenv:8000"
    assert config.heartbeat_interval == 15


def test_real_env_var_takes_priority_over_dotenv(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKEND_URL", "http://from-real-env:8000")
    env_file = tmp_path / ".env"
    env_file.write_text("BACKEND_URL=http://from-dotenv:8000\n", encoding="utf-8")

    config = load_config(dotenv_path=env_file)

    assert config.backend_url == "http://from-real-env:8000"


def test_config_repr_never_shows_real_token(monkeypatch, tmp_path):
    monkeypatch.setenv("BACKEND_URL", "http://backend:8000")
    monkeypatch.setenv("AGENT_TOKEN", "cok-gizli-token-degeri")
    config = load_config(dotenv_path=tmp_path / "nonexistent.env")

    assert "cok-gizli-token-degeri" not in repr(config)
