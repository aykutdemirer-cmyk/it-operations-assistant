import json

from agent.authentication import build_auth_header, load_local_state, redact_token, save_local_state


def test_redact_token_never_returns_full_value():
    token = "cok-gizli-token-degeri-1234567890"
    result = redact_token(token)
    assert token not in result
    assert result.endswith("7890")


def test_redact_token_handles_short_or_missing_token():
    assert redact_token(None) == "(yok)"
    assert redact_token("") == "(yok)"
    assert redact_token("ab") == "****"


def test_save_and_load_local_state_roundtrip(tmp_path):
    path = tmp_path / "state.json"
    save_local_state(path, agent_id="agent-1", token="secret-token")

    loaded = load_local_state(path)

    assert loaded == {"agent_id": "agent-1", "token": "secret-token"}


def test_load_local_state_returns_none_when_file_missing(tmp_path):
    assert load_local_state(tmp_path / "does-not-exist.json") is None


def test_load_local_state_returns_none_when_file_corrupted(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("not valid json{{{", encoding="utf-8")
    assert load_local_state(path) is None


def test_load_local_state_returns_none_when_shape_is_wrong(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(json.dumps({"something_else": True}), encoding="utf-8")
    assert load_local_state(path) is None


def test_build_auth_header_uses_bearer_scheme():
    assert build_auth_header("my-token") == {"Authorization": "Bearer my-token"}
