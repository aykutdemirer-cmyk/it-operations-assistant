"""`agent/winservice.py` için testler.

`pywin32` (servicemanager/win32event/win32service/win32serviceutil)
sahte (fake) modüllerle `sys.modules`'a enjekte edilir — bu testler
pywin32 kurulu OLMASA bile (ör. Linux CI) çalışır; gerçek Windows
Service Control Manager (SCM) hiç kullanılmaz. Gerçek SCM entegrasyonu
(`sc.exe create`/`start`/`stop`/`delete`) bu fazda GERÇEK bir Windows
makinede elle doğrulandı (bkz. docs/roadmap.md) — burada yalnızca bu
modülün KENDİ mantığı (graceful stop çağrısı, config hata yönetimi)
test edilir."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from agent.config import AgentConfig, ConfigError


@pytest.fixture
def fake_pywin32(monkeypatch):
    fake_servicemanager = types.ModuleType("servicemanager")
    fake_servicemanager.LogMsg = MagicMock()
    fake_servicemanager.LogErrorMsg = MagicMock()
    fake_servicemanager.EVENTLOG_INFORMATION_TYPE = 1
    fake_servicemanager.PYS_SERVICE_STARTED = 1
    fake_servicemanager.Initialize = MagicMock()
    fake_servicemanager.PrepareToHostSingle = MagicMock()
    fake_servicemanager.StartServiceCtrlDispatcher = MagicMock()

    fake_win32event = types.ModuleType("win32event")
    fake_win32event.CreateEvent = MagicMock(return_value="fake-event-handle")
    fake_win32event.SetEvent = MagicMock()
    fake_win32event.WaitForSingleObject = MagicMock()
    fake_win32event.INFINITE = -1

    fake_win32service = types.ModuleType("win32service")
    fake_win32service.SERVICE_STOP_PENDING = 3

    class _FakeServiceFramework:
        def __init__(self, args):
            self._args = args

        def ReportServiceStatus(self, status):
            pass

    fake_win32serviceutil = types.ModuleType("win32serviceutil")
    fake_win32serviceutil.ServiceFramework = _FakeServiceFramework
    fake_win32serviceutil.HandleCommandLine = MagicMock()

    modules = {
        "servicemanager": fake_servicemanager,
        "win32event": fake_win32event,
        "win32service": fake_win32service,
        "win32serviceutil": fake_win32serviceutil,
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    return modules


def _config(**overrides) -> AgentConfig:
    defaults = dict(backend_url="http://backend:8000", agent_id="a", agent_token="t")
    defaults.update(overrides)
    return AgentConfig(**defaults)


def test_build_service_class_declares_the_exact_expected_identity(fake_pywin32):
    from agent.winservice import _build_service_class

    service_class = _build_service_class()

    assert service_class._svc_name_ == "ITOpsAgent"
    assert service_class._svc_display_name_ == "IT Operations Assistant Telemetry Agent"


def test_svc_stop_calls_runtime_stop_and_sets_event(fake_pywin32):
    from agent.winservice import _build_service_class

    service_class = _build_service_class()
    service = service_class(args=[])
    service._runtime = MagicMock()

    service.SvcStop()

    service._runtime.stop.assert_called_once()
    fake_pywin32["win32event"].SetEvent.assert_called_once_with(service._stop_handle)


def test_svc_stop_does_not_crash_when_runtime_not_yet_started(fake_pywin32):
    """`SvcStop` teorik olarak `SvcDoRun` tamamen başlamadan önce
    çağrılabilir (ör. çok hızlı bir stop isteği) — `self._runtime`
    hâlâ `None` olabilir, çökmemeli."""
    from agent.winservice import _build_service_class

    service_class = _build_service_class()
    service = service_class(args=[])

    service.SvcStop()  # exception fırlatmamalı

    fake_pywin32["win32event"].SetEvent.assert_called_once()


def test_svc_do_run_logs_and_returns_when_config_invalid(fake_pywin32, tmp_path):
    from agent.winservice import _build_service_class

    service_class = _build_service_class()
    service = service_class(args=[])

    with (
        patch("agent.winservice.load_config", side_effect=ConfigError("BACKEND_URL zorunlu")),
        patch("agent.winservice._configure_logging"),
        # `_log_fatal_config_error` (bkz. `agent/main.py`) artık gerçekten
        # bir dosyaya da loglamayı DENER — testin çalışma dizinini
        # kirletmemesi için varsayılan log yolu `tmp_path`'e yönlendirilir.
        patch("agent.main._default_log_file_path", return_value=tmp_path / "agent.log"),
    ):
        service.SvcDoRun()  # exception fırlatmamalı

    fake_pywin32["servicemanager"].LogErrorMsg.assert_called_once()
    assert service._runtime is None
    assert "BACKEND_URL zorunlu" in (tmp_path / "agent.log").read_text(encoding="utf-8")


def test_svc_do_run_starts_runtime_thread_and_waits_for_stop(fake_pywin32):
    from agent.winservice import _build_service_class

    service_class = _build_service_class()
    service = service_class(args=[])

    created_threads = []

    class _FakeThread:
        def __init__(self, target, name, daemon):
            created_threads.append(name)
            self._target = target

        def start(self):
            pass  # gerçekten çalıştırma — AgentRuntime.start() sonsuz döngü

        def join(self, timeout=None):
            pass

    with (
        patch("agent.winservice.load_config", return_value=_config()),
        patch("agent.winservice._configure_logging"),
        patch("agent.winservice._add_file_logging"),
        patch("agent.winservice.threading.Thread", _FakeThread),
    ):
        service.SvcDoRun()

    assert "agent-runtime" in created_threads
    assert service._runtime is not None
    fake_pywin32["win32event"].WaitForSingleObject.assert_called_once_with(
        service._stop_handle, fake_pywin32["win32event"].INFINITE
    )


def test_svc_do_run_logs_unexpected_runtime_thread_exceptions(fake_pywin32, tmp_path, caplog):
    """Gerçek kullanıcı bildirimiyle bulunan bir hata: `AgentRuntime.
    start()`'tan sızan bir istisna, bu thread'i SESSİZCE öldürüyordu —
    `agent.log`'da "kayıt deneniyor" satırından sonra hiçbir şey
    görünmüyordu. `SvcDoRun`'ın thread sarmalayıcısı artık HERHANGİ bir
    istisnayı yakalayıp loglar (`AgentRuntime.start()`'ın KENDİ
    kayıt-hatası loglaması BİLE atlansa)."""
    import logging

    from agent.winservice import _build_service_class

    service_class = _build_service_class()
    service = service_class(args=[])

    captured_target = {}

    class _FakeThread:
        def __init__(self, target, name, daemon):
            captured_target["fn"] = target

        def start(self):
            captured_target["fn"]()  # gerçekten çağır — normalde ayrı thread'de çalışır

        def join(self, timeout=None):
            pass

    with (
        patch("agent.winservice.load_config", return_value=_config()),
        patch("agent.winservice._configure_logging"),
        patch("agent.winservice._add_file_logging"),
        patch("agent.winservice.threading.Thread", _FakeThread),
        patch("agent.winservice.AgentRuntime.start", side_effect=RuntimeError("beklenmeyen çöküş")),
        caplog.at_level(logging.ERROR, logger="agent.winservice"),
    ):
        service.SvcDoRun()  # exception fırlatmamalı — thread sarmalayıcı yakalar

    assert any("beklenmeyen" in record.getMessage().lower() for record in caplog.records)
