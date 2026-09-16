"""`agent/main.py` testleri — gerçek ağ isteği YOK, `BackendClient`
mock'lanır. `_Loop`'un retry/backoff/auth-failure davranışı gerçek
zamanlamayı beklememesi için `stop_event.wait` kısa aralıklarla
tetiklenir."""

import logging
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.client import BackendAuthenticationError, BackendUnavailableError
from agent.commands import CommandResult
from agent.config import AgentConfig, ConfigError
from agent.main import (
    AgentRuntime,
    EnrollmentCodeMissingError,
    _Loop,
    _add_file_logging,
    _default_log_file_path,
    _default_state_file_path,
    _log_fatal_config_error,
    _warn_if_insecure_backend,
    ensure_registered,
)


def _config(tmp_path, **overrides) -> AgentConfig:
    defaults = dict(backend_url="http://backend:8000", state_file=tmp_path / "state.json")
    defaults.update(overrides)
    return AgentConfig(**defaults)


def test_ensure_registered_prefers_env_supplied_identity(tmp_path):
    config = _config(tmp_path, agent_id="agent-from-env", agent_token="token-from-env")
    client = MagicMock()

    agent_id, token = ensure_registered(config, client)

    assert (agent_id, token) == ("agent-from-env", "token-from-env")
    client.register.assert_not_called()


def test_ensure_registered_uses_local_state_when_no_env_identity(tmp_path):
    config = _config(tmp_path)
    config.state_file.write_text('{"agent_id": "agent-from-state", "token": "token-from-state"}', encoding="utf-8")
    client = MagicMock()

    agent_id, token = ensure_registered(config, client)

    assert (agent_id, token) == ("agent-from-state", "token-from-state")
    client.register.assert_not_called()


def test_ensure_registered_registers_and_persists_when_unknown(tmp_path):
    config = _config(tmp_path, enrollment_code="ABC-DEF-123")
    client = MagicMock()
    client.register.return_value = {"agent_id": "new-agent-id", "token": "new-token"}

    agent_id, token = ensure_registered(config, client)

    assert (agent_id, token) == ("new-agent-id", "new-token")
    client.register.assert_called_once()
    sent_payload = client.register.call_args.args[0]
    assert sent_payload["enrollment_code"] == "ABC-DEF-123"
    saved = config.state_file.read_text(encoding="utf-8")
    assert "new-agent-id" in saved
    assert "new-token" in saved


def test_ensure_registered_raises_when_enrollment_code_missing_for_new_registration(tmp_path):
    config = _config(tmp_path)  # enrollment_code verilmedi
    client = MagicMock()

    with pytest.raises(EnrollmentCodeMissingError):
        ensure_registered(config, client)

    client.register.assert_not_called()


def test_ensure_registered_does_not_require_enrollment_code_when_identity_already_known(tmp_path):
    """Zaten kayıtlı bir agent için (env veya yerel state) enrollment
    kodu HİÇ istenmez — kod yalnızca YENİ kayıtlar içindir."""
    config = _config(tmp_path, agent_id="known-agent", agent_token="known-token")
    client = MagicMock()

    agent_id, token = ensure_registered(config, client)

    assert (agent_id, token) == ("known-agent", "known-token")


# --- Ağ Bağlantı Sorunu — kayıt hatası artık her zaman agent.log'a yazılır ---


def test_agent_runtime_start_logs_and_reraises_when_registration_fails(tmp_path, caplog):
    """Gerçek kullanıcı bildirimiyle bulunan bir hata: bir Windows
    Servisi olarak çalışırken (konsolsuz) `ensure_registered` başarısız
    olduğunda önceden hiçbir şey `agent.log`'a yazılmıyordu — yalnızca
    "kayıt deneniyor" satırından sonra süreç sessizce ölüyordu (thread
    excepthook'u yalnızca stderr'e yazıyordu, kimse görmüyordu)."""
    config = _config(tmp_path, enrollment_code="ABC-DEF-GHI")
    runtime = AgentRuntime(config)

    with (
        patch(
            "agent.main.ensure_registered",
            side_effect=BackendAuthenticationError("HTTP 401: Enrollment code süresi dolmuş"),
        ),
        caplog.at_level(logging.ERROR, logger="agent.main"),
        pytest.raises(BackendAuthenticationError),
    ):
        runtime.start()

    assert any("Enrollment code süresi dolmuş" in record.getMessage() for record in caplog.records)


def test_agent_runtime_start_logs_enrollment_code_missing_error_too(tmp_path, caplog):
    config = _config(tmp_path)  # enrollment_code yok, agent_id/token da yok
    runtime = AgentRuntime(config)

    with (
        caplog.at_level(logging.ERROR, logger="agent.main"),
        pytest.raises(EnrollmentCodeMissingError),
    ):
        runtime.start()

    assert any("başlatılamıyor" in record.getMessage() for record in caplog.records)


def test_warn_if_insecure_backend_logs_when_http(tmp_path, caplog):
    config = _config(tmp_path, backend_url="http://insecure-backend:8000")

    with caplog.at_level(logging.WARNING, logger="agent.main"):
        _warn_if_insecure_backend(config)

    assert any("http://" in record.getMessage() for record in caplog.records)


def test_warn_if_insecure_backend_silent_when_https(tmp_path, caplog):
    config = _config(tmp_path, backend_url="https://secure-backend:8000")

    with caplog.at_level(logging.WARNING, logger="agent.main"):
        _warn_if_insecure_backend(config)

    assert caplog.records == []


# --- Ağ Bağlantı Sorunu — Debug/Logging iyileştirmesi ---


def test_log_fatal_config_error_writes_to_log_file(tmp_path, caplog, monkeypatch):
    """Gerçek kullanıcı senaryosu: `BACKEND_URL` eksik/geçersizken bir
    Windows Servisi/systemd daemon'u (konsolsuz) olarak çalışıyor —
    önceden bu hata hiçbir dosyaya yazılmıyordu (yalnızca kimsenin
    görmediği stderr). Artık `AGENT_LOG_FILE` set edilmemiş olsa bile
    en azından varsayılan konuma (`_default_log_file_path`) bir dosya
    handler'ı eklenip hata oraya da yazılmalı."""
    monkeypatch.delenv("AGENT_LOG_FILE", raising=False)
    log_path = tmp_path / "agent.log"
    with patch("agent.main._default_log_file_path", return_value=log_path):
        with caplog.at_level(logging.ERROR, logger="agent.main"):
            _log_fatal_config_error(ConfigError("BACKEND_URL zorunlu"))

    assert log_path.exists()
    assert "BACKEND_URL zorunlu" in log_path.read_text(encoding="utf-8")
    assert any("BACKEND_URL zorunlu" in record.getMessage() for record in caplog.records)


def test_log_fatal_config_error_respects_explicit_agent_log_file_env(tmp_path, monkeypatch):
    custom_log = tmp_path / "custom" / "agent.log"
    monkeypatch.setenv("AGENT_LOG_FILE", str(custom_log))

    _log_fatal_config_error(ConfigError("test hatası"))

    assert custom_log.exists()
    assert "test hatası" in custom_log.read_text(encoding="utf-8")


def test_log_fatal_config_error_never_raises_when_file_logging_fails(tmp_path, capsys):
    """Dosyaya yazma başarısız olsa bile (ör. izin hatası) fonksiyon
    exception FIRLATMAMALI — en azından stderr'e yazılmış olması
    yeterli (bkz. `_add_file_logging`'in kendi OSError yakalaması)."""
    unwritable_dir = tmp_path / "no-such-parent" / "sub" / "sub2"
    with patch("agent.main._default_log_file_path", return_value=unwritable_dir / "agent.log"):
        with patch("pathlib.Path.mkdir", side_effect=OSError("izin reddedildi")):
            _log_fatal_config_error(ConfigError("BACKEND_URL zorunlu"))  # exception fırlatmamalı

    captured = capsys.readouterr()
    assert "BACKEND_URL zorunlu" in captured.err


def test_loop_retries_on_backend_unavailable_then_succeeds():
    stop_event = threading.Event()
    call_count = {"n": 0}

    def action():
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise BackendUnavailableError("boom")
        stop_event.set()  # üçüncü denemede başarı — döngüyü durdur

    on_auth_failure = MagicMock()
    loop = _Loop("test", interval=0, action=action, stop_event=stop_event, on_auth_failure=on_auth_failure)

    # Gerçek zamanlamayı beklemeden test etmek için backoff çizelgesini kısalt.
    import agent.main as main_module

    original_schedule = main_module._BACKOFF_SCHEDULE
    main_module._BACKOFF_SCHEDULE = (0, 0, 0, 0, 0)
    try:
        loop.run()
    finally:
        main_module._BACKOFF_SCHEDULE = original_schedule

    assert call_count["n"] == 3
    on_auth_failure.assert_not_called()


def test_loop_stops_and_calls_on_auth_failure_when_token_invalid():
    stop_event = threading.Event()

    def action():
        raise BackendAuthenticationError("token geçersiz")

    on_auth_failure = MagicMock(side_effect=lambda: stop_event.set())
    loop = _Loop("test", interval=0, action=action, stop_event=stop_event, on_auth_failure=on_auth_failure)

    loop.run()

    on_auth_failure.assert_called_once()


def test_loop_continues_after_validation_error_without_backoff():
    from agent.client import BackendValidationError

    stop_event = threading.Event()
    call_count = {"n": 0}

    def action():
        call_count["n"] += 1
        if call_count["n"] >= 2:
            stop_event.set()
            return
        raise BackendValidationError("geçersiz payload")

    loop = _Loop("test", interval=0, action=action, stop_event=stop_event, on_auth_failure=MagicMock())
    loop.run()

    assert call_count["n"] == 2


# --- AgentRuntime._poll_and_execute_commands (Faz 33) ---


def _runtime(tmp_path) -> AgentRuntime:
    runtime = AgentRuntime(_config(tmp_path))
    runtime._agent_id = "agent-1"
    runtime._token = "token-1"
    runtime._client = MagicMock()
    return runtime


def test_poll_and_execute_commands_runs_and_reports_success(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._client.get_pending_commands.return_value = [
        {"id": "cmd-1", "command_type": "kill_process", "action": "kill", "target": "1234"}
    ]

    with patch("agent.main.remote_commands.execute", return_value=CommandResult(True, "PID 1234 sonlandırıldı")):
        runtime._poll_and_execute_commands()

    runtime._client.report_command_result.assert_called_once_with(
        "token-1", "agent-1", "cmd-1", "succeeded", "PID 1234 sonlandırıldı"
    )


def test_poll_and_execute_commands_reports_failure(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._client.get_pending_commands.return_value = [
        {"id": "cmd-1", "command_type": "service_control", "action": "stop", "target": "spooler"}
    ]

    with patch("agent.main.remote_commands.execute", return_value=CommandResult(False, "reddedildi")):
        runtime._poll_and_execute_commands()

    runtime._client.report_command_result.assert_called_once_with(
        "token-1", "agent-1", "cmd-1", "failed", "reddedildi"
    )


def test_poll_and_execute_commands_survives_unexpected_exception(tmp_path):
    """Bir komutun beklenmeyen hatası döngüyü ÇÖKERTMEZ — `failed`
    olarak raporlanır, diğer komutlar (varsa) etkilenmez."""
    runtime = _runtime(tmp_path)
    runtime._client.get_pending_commands.return_value = [
        {"id": "cmd-1", "command_type": "kill_process", "action": "kill", "target": "1234"}
    ]

    with patch("agent.main.remote_commands.execute", side_effect=RuntimeError("boom")):
        runtime._poll_and_execute_commands()

    args = runtime._client.report_command_result.call_args.args
    assert args[3] == "failed"
    assert "Beklenmeyen hata" in args[4]


def test_poll_and_execute_commands_noop_when_no_pending(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._client.get_pending_commands.return_value = []

    runtime._poll_and_execute_commands()

    runtime._client.report_command_result.assert_not_called()
    runtime._client.send_inventory.assert_not_called()


def test_poll_and_execute_commands_sends_fresh_inventory_after_processing(tmp_path):
    """Gerçek kullanıcı bildirimi: servis durdurulduktan sonra UI'da
    hâlâ 'çalışıyor' görünüyordu — çünkü envanter yalnızca normal
    `inventory_interval`de (varsayılan 300s) yenileniyordu. Artık en az
    bir komut işlendiyse HEMEN taze bir envanter gönderiliyor."""
    runtime = _runtime(tmp_path)
    runtime._client.get_pending_commands.return_value = [
        {"id": "cmd-1", "command_type": "service_control", "action": "stop", "target": "spooler"}
    ]

    with patch("agent.main.remote_commands.execute", return_value=CommandResult(True, "durduruldu")):
        runtime._poll_and_execute_commands()

    runtime._client.send_inventory.assert_called_once()


def test_poll_and_execute_commands_handles_refresh_inventory_directly(tmp_path):
    """Faz 33.1 — 'Yenile' butonu: `refresh_inventory` komutu `agent/
    commands.py`'nin OS-dispatcher'ından GEÇMEMELİ, doğrudan
    `_send_inventory()`'yi tetiklemeli."""
    runtime = _runtime(tmp_path)
    runtime._client.get_pending_commands.return_value = [
        {"id": "cmd-1", "command_type": "refresh_inventory", "action": "collect", "target": "inventory"}
    ]

    with patch("agent.main.remote_commands.execute") as mock_execute:
        runtime._poll_and_execute_commands()

    mock_execute.assert_not_called()
    runtime._client.send_inventory.assert_called_once()
    runtime._client.report_command_result.assert_called_once_with(
        "token-1", "agent-1", "cmd-1", "succeeded", "Envanter tazelendi"
    )


def test_poll_and_execute_commands_does_not_double_send_inventory(tmp_path):
    """Aynı turda hem `refresh_inventory` hem bir `service_control`
    komutu varsa envanter yalnızca BİR KEZ gönderilmeli."""
    runtime = _runtime(tmp_path)
    runtime._client.get_pending_commands.return_value = [
        {"id": "cmd-1", "command_type": "refresh_inventory", "action": "collect", "target": "inventory"},
        {"id": "cmd-2", "command_type": "service_control", "action": "stop", "target": "spooler"},
    ]

    with patch("agent.main.remote_commands.execute", return_value=CommandResult(True, "durduruldu")):
        runtime._poll_and_execute_commands()

    runtime._client.send_inventory.assert_called_once()


def test_poll_and_execute_commands_refresh_inventory_failure_reported_as_failed(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._client.get_pending_commands.return_value = [
        {"id": "cmd-1", "command_type": "refresh_inventory", "action": "collect", "target": "inventory"}
    ]
    runtime._client.send_inventory.side_effect = RuntimeError("backend geçici ulaşılamaz")

    runtime._poll_and_execute_commands()

    args = runtime._client.report_command_result.call_args.args
    assert args[3] == "failed"


def test_poll_and_execute_commands_inventory_refresh_failure_does_not_crash(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._client.get_pending_commands.return_value = [
        {"id": "cmd-1", "command_type": "kill_process", "action": "kill", "target": "1234"}
    ]
    runtime._client.send_inventory.side_effect = RuntimeError("backend geçici ulaşılamaz")

    with patch("agent.main.remote_commands.execute", return_value=CommandResult(True, "ok")):
        runtime._poll_and_execute_commands()  # exception fırlatmamalı

    runtime._client.report_command_result.assert_called_once()


# --- Windows Update Tarama Motoru: "Güncellemeleri Kontrol Et" komutu ---


def test_poll_and_execute_commands_handles_check_updates_directly(tmp_path):
    """`check_updates` komutu `agent/commands.py`'nin OS-dispatcher'ından
    GEÇMEMELİ, doğrudan `_send_windows_updates()`'i tetiklemeli (bkz.
    `refresh_inventory` ile AYNI özel-durum deseni)."""
    from agent.collectors.windows_updates import UpdateItem, UpdateScanResult

    runtime = _runtime(tmp_path)
    runtime._client.get_pending_commands.return_value = [
        {"id": "cmd-1", "command_type": "check_updates", "action": "scan", "target": "self"}
    ]
    fake_result = UpdateScanResult(
        scan_method="com", is_admin=True,
        updates=[UpdateItem(kb_number="KB1", title="Update 1")],
        error=None,
    )

    with (
        patch("agent.main.remote_commands.execute") as mock_execute,
        patch("agent.main.windows_updates.scan_pending_updates", return_value=fake_result),
    ):
        runtime._poll_and_execute_commands()

    mock_execute.assert_not_called()
    runtime._client.send_windows_updates.assert_called_once()
    runtime._client.report_command_result.assert_called_once_with(
        "token-1", "agent-1", "cmd-1", "succeeded", "1 güncelleme bulundu (com)"
    )


def test_poll_and_execute_commands_check_updates_reports_failure_when_scan_unavailable(tmp_path):
    from agent.collectors.windows_updates import UpdateScanResult

    runtime = _runtime(tmp_path)
    runtime._client.get_pending_commands.return_value = [
        {"id": "cmd-1", "command_type": "check_updates", "action": "scan", "target": "self"}
    ]
    fake_result = UpdateScanResult(scan_method="unavailable", is_admin=True, updates=[], error="Hem COM hem PowerShell başarısız")

    with patch("agent.main.windows_updates.scan_pending_updates", return_value=fake_result):
        runtime._poll_and_execute_commands()

    runtime._client.report_command_result.assert_called_once_with(
        "token-1", "agent-1", "cmd-1", "failed", "Hem COM hem PowerShell başarısız"
    )


def test_poll_and_execute_commands_check_updates_survives_unexpected_exception(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._client.get_pending_commands.return_value = [
        {"id": "cmd-1", "command_type": "check_updates", "action": "scan", "target": "self"}
    ]

    with patch("agent.main.windows_updates.scan_pending_updates", side_effect=RuntimeError("boom")):
        runtime._poll_and_execute_commands()  # exception fırlatmamalı

    args = runtime._client.report_command_result.call_args.args
    assert args[3] == "failed"
    assert "boom" in args[4]


# --- Windows Update Yükleme: "install_update" komutu ---


def test_poll_and_execute_commands_handles_install_update_directly(tmp_path):
    """`install_update` komutu `agent/commands.py`'nin OS-dispatcher'ından
    GEÇMEMELİ, doğrudan `windows_updates.install_updates()`'i
    tetiklemeli; başarılı bir yüklemeden SONRA taze bir tarama
    gönderilmeli (yüklenen KB artık listede görünmemeli)."""
    from agent.collectors.windows_updates import InstallResult, UpdateScanResult

    runtime = _runtime(tmp_path)
    runtime._client.get_pending_commands.return_value = [
        {"id": "cmd-1", "command_type": "install_update", "action": "install", "target": "KB1234567"}
    ]
    fake_install_result = InstallResult(True, False, "1 güncelleme başarıyla yüklendi", installed_count=1)
    fake_scan_result = UpdateScanResult(scan_method="com", is_admin=True, updates=[], error=None)

    with (
        patch("agent.main.remote_commands.execute") as mock_execute,
        patch("agent.main.windows_updates.install_updates", return_value=fake_install_result) as mock_install,
        patch("agent.main.windows_updates.scan_pending_updates", return_value=fake_scan_result),
    ):
        runtime._poll_and_execute_commands()

    mock_execute.assert_not_called()
    mock_install.assert_called_once_with("KB1234567")
    runtime._client.report_command_result.assert_called_once_with(
        "token-1", "agent-1", "cmd-1", "succeeded", "1 güncelleme başarıyla yüklendi"
    )
    # Komut sonrası tazeleme: yüklemeden SONRA yeni bir tarama gönderildi.
    runtime._client.send_windows_updates.assert_called_once()


def test_poll_and_execute_commands_install_update_reports_failure(tmp_path):
    from agent.collectors.windows_updates import InstallResult, UpdateScanResult

    runtime = _runtime(tmp_path)
    runtime._client.get_pending_commands.return_value = [
        {"id": "cmd-1", "command_type": "install_update", "action": "install", "target": "all"}
    ]
    fake_install_result = InstallResult(False, False, "İndirme başarısız oldu (ResultCode=4)")
    fake_scan_result = UpdateScanResult(scan_method="com", is_admin=True, updates=[], error=None)

    with (
        patch("agent.main.windows_updates.install_updates", return_value=fake_install_result),
        patch("agent.main.windows_updates.scan_pending_updates", return_value=fake_scan_result),
    ):
        runtime._poll_and_execute_commands()

    runtime._client.report_command_result.assert_called_once_with(
        "token-1", "agent-1", "cmd-1", "failed", "İndirme başarısız oldu (ResultCode=4)"
    )


def test_poll_and_execute_commands_install_update_survives_unexpected_exception(tmp_path):
    runtime = _runtime(tmp_path)
    runtime._client.get_pending_commands.return_value = [
        {"id": "cmd-1", "command_type": "install_update", "action": "install", "target": "all"}
    ]

    with patch("agent.main.windows_updates.install_updates", side_effect=RuntimeError("boom")):
        runtime._poll_and_execute_commands()  # exception fırlatmamalı

    args = runtime._client.report_command_result.call_args.args
    assert args[3] == "failed"
    assert "boom" in args[4]


def test_poll_and_execute_commands_install_update_refresh_failure_does_not_crash(tmp_path):
    """Yükleme sonrası tazeleme taraması başarısız olsa bile (ör.
    backend geçici ulaşılamaz) komutun kendi sonucu ZATEN raporlanmış
    olur — döngü çökmez."""
    from agent.collectors.windows_updates import InstallResult

    runtime = _runtime(tmp_path)
    runtime._client.get_pending_commands.return_value = [
        {"id": "cmd-1", "command_type": "install_update", "action": "install", "target": "all"}
    ]
    fake_install_result = InstallResult(True, False, "1 güncelleme başarıyla yüklendi", installed_count=1)

    with (
        patch("agent.main.windows_updates.install_updates", return_value=fake_install_result),
        patch("agent.main.windows_updates.scan_pending_updates", side_effect=RuntimeError("backend down")),
    ):
        runtime._poll_and_execute_commands()  # exception fırlatmamalı

    runtime._client.report_command_result.assert_called_once_with(
        "token-1", "agent-1", "cmd-1", "succeeded", "1 güncelleme başarıyla yüklendi"
    )


def test_start_adds_commands_loop_only_when_enabled(tmp_path):
    """`enable_remote_commands=False` (varsayılan) iken 4. thread hiç
    başlamamalı — `start()`'ı gerçekten çalıştırmadan, yalnızca loop
    listesi oluşturma mantığını `threading.Thread`'i mock'layarak
    doğrular."""
    config = _config(tmp_path, enable_remote_commands=True, agent_id="a", agent_token="t")
    runtime = AgentRuntime(config)

    created_thread_names = []

    class _FakeThread:
        def __init__(self, target, name, daemon):
            created_thread_names.append(name)

        def start(self):
            pass

        def join(self, timeout=None):
            pass

    with (
        patch("agent.main.threading.Thread", _FakeThread),
        patch("agent.main.signal.signal"),
        patch.object(runtime._stop_event, "is_set", return_value=True),
    ):
        runtime.start()

    assert "commands" in created_thread_names


def test_start_omits_commands_loop_when_disabled(tmp_path):
    config = _config(tmp_path, enable_remote_commands=False, agent_id="a", agent_token="t")
    runtime = AgentRuntime(config)

    created_thread_names = []

    class _FakeThread:
        def __init__(self, target, name, daemon):
            created_thread_names.append(name)

        def start(self):
            pass

        def join(self, timeout=None):
            pass

    with (
        patch("agent.main.threading.Thread", _FakeThread),
        patch("agent.main.signal.signal"),
        patch.object(runtime._stop_event, "is_set", return_value=True),
    ):
        runtime.start()

    assert "commands" not in created_thread_names


def test_start_adds_windows_updates_loop_on_windows_when_enabled(tmp_path):
    config = _config(tmp_path, agent_id="a", agent_token="t")
    assert config.enable_windows_updates_scan is True  # varsayılan
    runtime = AgentRuntime(config)

    created_thread_names = []

    class _FakeThread:
        def __init__(self, target, name, daemon):
            created_thread_names.append(name)

        def start(self):
            pass

        def join(self, timeout=None):
            pass

    with (
        patch("agent.main.threading.Thread", _FakeThread),
        patch("agent.main.signal.signal"),
        patch("agent.main.current_os", return_value="windows"),
        patch.object(runtime._stop_event, "is_set", return_value=True),
    ):
        runtime.start()

    assert "windows-updates" in created_thread_names


def test_start_omits_windows_updates_loop_when_disabled(tmp_path):
    config = _config(tmp_path, agent_id="a", agent_token="t", enable_windows_updates_scan=False)
    runtime = AgentRuntime(config)

    created_thread_names = []

    class _FakeThread:
        def __init__(self, target, name, daemon):
            created_thread_names.append(name)

        def start(self):
            pass

        def join(self, timeout=None):
            pass

    with (
        patch("agent.main.threading.Thread", _FakeThread),
        patch("agent.main.signal.signal"),
        patch("agent.main.current_os", return_value="windows"),
        patch.object(runtime._stop_event, "is_set", return_value=True),
    ):
        runtime.start()

    assert "windows-updates" not in created_thread_names


def test_start_omits_windows_updates_loop_on_linux_even_when_enabled(tmp_path):
    config = _config(tmp_path, agent_id="a", agent_token="t", enable_windows_updates_scan=True)
    runtime = AgentRuntime(config)

    created_thread_names = []

    class _FakeThread:
        def __init__(self, target, name, daemon):
            created_thread_names.append(name)

        def start(self):
            pass

        def join(self, timeout=None):
            pass

    with (
        patch("agent.main.threading.Thread", _FakeThread),
        patch("agent.main.signal.signal"),
        patch("agent.main.current_os", return_value="linux"),
        patch.object(runtime._stop_event, "is_set", return_value=True),
    ):
        runtime.start()

    assert "windows-updates" not in created_thread_names


def test_send_windows_updates_builds_payload_and_calls_client(tmp_path):
    from agent.collectors.windows_updates import UpdateItem, UpdateScanResult

    runtime = _runtime(tmp_path)
    fake_result = UpdateScanResult(
        scan_method="com", is_admin=True,
        updates=[UpdateItem(kb_number="KB123", title="Update 1", description="desc", size_bytes=100)],
        error=None,
    )
    with patch("agent.main.windows_updates.scan_pending_updates", return_value=fake_result):
        runtime._send_windows_updates()

    runtime._client.send_windows_updates.assert_called_once()
    call_args = runtime._client.send_windows_updates.call_args
    payload = call_args.args[2]
    assert payload["scan_method"] == "com"
    assert payload["is_admin"] is True
    assert payload["updates"] == [
        {"kb_number": "KB123", "title": "Update 1", "description": "desc", "size_bytes": 100}
    ]
    assert payload["error"] is None
    assert "collected_at" in payload


# --- Faz 37: power_control sonrası telemetry tazeleme ---


def test_poll_and_execute_commands_sends_telemetry_after_logoff(tmp_path):
    """Gerçek senaryo: bir kullanıcının oturumu uzaktan kapatıldıktan
    sonra UI'daki 'Aktif Oturum Sayısı' HEMEN güncellenmeli — bu bilgi
    inventory'de DEĞİL telemetry'de yaşıyor (bkz. Faz 34)."""
    runtime = _runtime(tmp_path)
    runtime._client.get_pending_commands.return_value = [
        {"id": "cmd-1", "command_type": "power_control", "action": "logoff", "target": "alice"}
    ]

    with patch("agent.main.remote_commands.execute", return_value=CommandResult(True, "ok")):
        runtime._poll_and_execute_commands()

    runtime._client.send_telemetry.assert_called_once()
    runtime._client.send_inventory.assert_not_called()


def test_poll_and_execute_commands_does_not_send_telemetry_after_reboot(tmp_path):
    """reboot/shutdown sonrası tazeleme ANLAMSIZ — makine zaten
    kapanıyor, agent birazdan ölecek."""
    runtime = _runtime(tmp_path)
    runtime._client.get_pending_commands.return_value = [
        {"id": "cmd-1", "command_type": "power_control", "action": "reboot", "target": "system"}
    ]

    with patch("agent.main.remote_commands.execute", return_value=CommandResult(True, "ok")):
        runtime._poll_and_execute_commands()

    runtime._client.send_telemetry.assert_not_called()
    runtime._client.send_inventory.assert_not_called()


# --- Windows Servisi/systemd daemon otomasyonu: dosya loglama + ana
# thread dışında sinyal kaydı (bkz. agent/winservice.py) ---


def test_start_does_not_crash_when_signal_registration_fails_outside_main_thread():
    """`signal.signal()` yalnızca ana thread'de çağrılabilir — Windows
    Servisi bağlamında (`agent/winservice.py`) `AgentRuntime.start()`
    bir arka plan thread'inden çalıştırılır. Bu durumda `ValueError`
    fırlar; `start()` çökmemeli, yalnızca sinyal kaydını sessizce
    atlamalı (kapatma `stop()`'un doğrudan çağrılmasıyla gelir)."""
    config = _config(Path("."), agent_id="a", agent_token="t")
    runtime = AgentRuntime(config)

    class _FakeThread:
        def __init__(self, target, name, daemon):
            pass

        def start(self):
            pass

        def join(self, timeout=None):
            pass

    with (
        patch("agent.main.threading.Thread", _FakeThread),
        patch("agent.main.signal.signal", side_effect=ValueError("signal only works in main thread")),
        patch.object(runtime._stop_event, "is_set", return_value=True),
    ):
        runtime.start()  # exception fırlatmamalı


def test_default_log_file_path_uses_cwd_in_dev_mode():
    assert _default_log_file_path() == Path(".") / "agent.log"


def test_default_state_file_path_uses_cwd_in_dev_mode():
    assert _default_state_file_path() == Path(".itops-agent-state.json")


def test_add_file_logging_creates_rotating_handler(tmp_path):
    log_path = tmp_path / "logs" / "agent.log"
    root_logger = logging.getLogger()
    handlers_before = list(root_logger.handlers)
    level_before = root_logger.level

    try:
        root_logger.setLevel(logging.INFO)
        _add_file_logging(log_path)
        logging.getLogger("agent.main").info("test mesajı")

        assert log_path.exists()
        assert "test mesajı" in log_path.read_text(encoding="utf-8")
    finally:
        root_logger.setLevel(level_before)
        for handler in list(root_logger.handlers):
            if handler not in handlers_before:
                root_logger.removeHandler(handler)
                handler.close()


def test_add_file_logging_falls_back_gracefully_when_path_unwritable(tmp_path, caplog):
    """Dosya yazılamıyorsa (ör. izin hatası) agent ÇÖKMEMELİ — yalnızca
    bir uyarı loglanır."""
    unwritable_parent = tmp_path / "not-a-directory"
    unwritable_parent.write_text("bu bir dosya, dizin değil", encoding="utf-8")
    log_path = unwritable_parent / "agent.log"

    with caplog.at_level(logging.WARNING):
        _add_file_logging(log_path)  # exception fırlatmamalı

    assert any("Dosya loglama başlatılamadı" in record.message for record in caplog.records)
