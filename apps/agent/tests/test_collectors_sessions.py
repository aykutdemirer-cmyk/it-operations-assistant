from unittest.mock import MagicMock, patch

from agent.collectors import sessions


def test_collect_sessions_delegates_to_platform_module():
    fake_platform = MagicMock()
    fake_platform.list_sessions.return_value = [
        {"username": "Administrator", "session_name": "rdp-tcp#1", "status": "active", "logon_time": "9/2/2026 8:57 AM"}
    ]

    with patch("agent.collectors.sessions.agent_platform.resolve", return_value=fake_platform):
        result = sessions.collect_sessions()

    assert result[0]["username"] == "Administrator"


def test_collect_sessions_returns_empty_list_when_platform_module_raises():
    with patch("agent.collectors.sessions.agent_platform.resolve", side_effect=RuntimeError("boom")):
        assert sessions.collect_sessions() == []


def test_summarize_sessions_empty_list():
    assert sessions.summarize_sessions([]) == (None, 0)


def test_summarize_sessions_counts_active_and_disconnected():
    session_list = [
        {"username": "alice", "status": "active", "logon_time": "9/2/2026 8:00 AM"},
        {"username": "bob", "status": "disconnected", "logon_time": "9/2/2026 9:00 AM"},
    ]
    _, count = sessions.summarize_sessions(session_list)
    assert count == 2


def test_summarize_sessions_picks_most_recent_logon_time_windows_format():
    session_list = [
        {"username": "alice", "status": "active", "logon_time": "9/2/2026 8:00 AM"},
        {"username": "bob", "status": "active", "logon_time": "9/2/2026 9:00 AM"},
    ]
    last_user, _ = sessions.summarize_sessions(session_list)
    assert last_user == "bob"


def test_summarize_sessions_picks_most_recent_logon_time_tr_locale_format():
    """Gerçek bir Windows makinesinde (tr-TR yerel ayarı) bulundu —
    `quser` bu ortamda `9/2/2026 8:57 AM` DEĞİL `1.09.2026 16:20`
    formatında zaman damgası üretiyor."""
    session_list = [
        {"username": "alice", "status": "active", "logon_time": "1.09.2026 08:00"},
        {"username": "bob", "status": "active", "logon_time": "1.09.2026 16:20"},
    ]
    last_user, _ = sessions.summarize_sessions(session_list)
    assert last_user == "bob"


def test_summarize_sessions_picks_most_recent_logon_time_linux_format():
    session_list = [
        {"username": "alice", "status": "active", "logon_time": "2026-09-02 08:00"},
        {"username": "bob", "status": "active", "logon_time": "2026-09-02 09:00"},
    ]
    last_user, _ = sessions.summarize_sessions(session_list)
    assert last_user == "bob"


def test_summarize_sessions_falls_back_to_first_entry_when_logon_time_unparseable():
    session_list = [
        {"username": "alice", "status": "active", "logon_time": "not-a-real-timestamp"},
        {"username": "bob", "status": "active", "logon_time": None},
    ]
    last_user, _ = sessions.summarize_sessions(session_list)
    assert last_user == "alice"
