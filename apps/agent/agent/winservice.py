"""Windows Service (SCM) wrapper — yalnızca Windows'ta, yalnızca
`packaging/windows/`'un servis build'inde kullanılır.

**Neden gerekli** (basit bir `sc.exe create binPath="...\\itops-agent.exe
start"` YETERLİ DEĞİL): Windows Service Control Manager (SCM), bir
servis olarak başlattığı sürecin `StartServiceCtrlDispatcher`'ı
çağırmasını ve `SetServiceStatus` ile durumunu bildirmesini BEKLER.
Bunu yapmayan sıradan bir konsol EXE'si SCM tarafından "zamanında yanıt
vermedi" (hata 1053) ile başarısız sayılır VE `sc stop` çağrıldığında
GERÇEK bir graceful shutdown sinyali (SIGTERM benzeri) ALMAZ — SCM
timeout sonunda süreci `TerminateProcess` ile SERT keser. Bu modül
`pywin32`'nin `win32serviceutil.ServiceFramework`'ünü implemente ederek
SCM protokolüne doğru şekilde katılır; `SvcStop` `AgentRuntime.stop()`'ı
ÇAĞIRIR (mevcut SIGINT/SIGTERM yolundaki AYNI `_stop_event` +
`thread.join(timeout=...)` mekanizması) — `TerminateProcess` ile sert
kesme YOK, gerçek graceful shutdown.

Kayıt/kontrol yine de kullanıcının istediği gibi düz `sc.exe create` /
`sc start` / `sc stop` / `sc delete` ile yapılabilir (bkz. `agent/
scripts/install_windows_service.ps1`) — pywin32 ile build edilmiş bir
EXE, SCM protokolünü doğru implemente ettiği için bu komutlarla tam
uyumludur; script'lerin kendisi DEĞİŞMEDİ.

`pywin32` yalnızca `packaging/windows/requirements-build.txt`'e
eklendi — ana `requirements.txt`'e DEĞİL (Linux'ta hiç mevcut değil,
systemd tarafı bu modülü hiç import etmez)."""

from __future__ import annotations

import logging
import threading

from agent.config import ConfigError, load_config
from agent.main import (
    AgentRuntime,
    _add_file_logging,
    _configure_logging,
    _default_dotenv_path,
    _default_state_file_path,
    _log_fatal_config_error,
)

logger = logging.getLogger("agent.winservice")


def _import_pywin32():
    """pywin32 içe aktarımını geciktirir — bu modül yanlışlıkla
    Linux'ta import edilirse (ör. bir test koleksiyonu sırasında)
    `ImportError` yerine modülün KENDİSİ hâlâ import edilebilsin diye
    (testler pywin32'yi mock'layabilsin) gerçek kullanım anına kadar
    ertelenir."""
    import servicemanager
    import win32event
    import win32service
    import win32serviceutil

    return servicemanager, win32event, win32service, win32serviceutil


def _build_service_class():
    servicemanager, win32event, win32service, win32serviceutil = _import_pywin32()

    class ITOpsAgentService(win32serviceutil.ServiceFramework):
        # `agent/scripts/install_windows_service.ps1`'deki `sc create`
        # çağrısıyla BİREBİR eşleşmeli (kullanıcı isteği — bkz. modül
        # docstring'i).
        _svc_name_ = "ITOpsAgent"
        _svc_display_name_ = "IT Operations Assistant Telemetry Agent"
        _svc_description_ = (
            "Collects and reports system telemetry/inventory to the "
            "IT Operations Assistant backend."
        )

        def __init__(self, args):
            super().__init__(args)
            self._stop_handle = win32event.CreateEvent(None, 0, 0, None)
            self._runtime: AgentRuntime | None = None
            self._runtime_thread: threading.Thread | None = None

        def SvcStop(self):
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            logger.info("SCM stop isteği alındı — graceful shutdown başlatılıyor")
            if self._runtime is not None:
                self._runtime.stop()
            win32event.SetEvent(self._stop_handle)

        def SvcDoRun(self):
            servicemanager.LogMsg(
                servicemanager.EVENTLOG_INFORMATION_TYPE,
                servicemanager.PYS_SERVICE_STARTED,
                (self._svc_name_, ""),
            )
            _configure_logging()
            try:
                config = load_config(
                    dotenv_path=_default_dotenv_path(), default_state_file=_default_state_file_path()
                )
            except ConfigError as exc:
                # `agent.log`'a da yazar (bkz. `_log_fatal_config_error`
                # docstring'i — Ağ Bağlantı Sorunu debug iyileştirmesi);
                # Windows Event Log'a yazma (`LogErrorMsg`) AYRICA
                # korunur, servis bağlamında ikinci bir görünürlük yolu.
                _log_fatal_config_error(exc)
                servicemanager.LogErrorMsg(f"ITOpsAgent yapılandırma hatası: {exc}")
                return
            _add_file_logging(config.log_file)

            self._runtime = AgentRuntime(config)

            def _run_runtime() -> None:
                # `AgentRuntime.start()` kayıt hatalarını KENDİSİ zaten
                # `agent.log`'a yazıp yeniden fırlatıyor (bkz. o
                # fonksiyonun docstring'i) — ama bu thread'in KENDİSİ
                # hiçbir üst seviye handler'a bağlı değil: bir istisna
                # buradan sızarsa Python'un varsayılan thread excepthook'u
                # yalnızca stderr'e yazar (bir Windows Servisi'nde
                # kimsenin görmediği bir yer). Gerçek kullanıcı
                # bildirimiyle bulunan bir hata: agent.log "kayıt
                # deneniyor" satırından sonra SESSİZCE duruyordu. Bu
                # sarmalayıcı SON bir güvenlik ağı — beklenmeyen HERHANGİ
                # bir istisnayı da (yalnızca kayıt hatalarını değil)
                # `agent.log`'a yazar.
                try:
                    self._runtime.start()
                except Exception:
                    logger.exception("Agent runtime beklenmeyen bir hatayla durdu")

            # `AgentRuntime.start()` kendi içinde sonsuz döngü —
            # SCM'nin kendi thread'ini BLOKE ETMEMESİ için ayrı bir
            # thread'de çalıştırılır (bkz. `main.py::AgentRuntime.start`
            # — sinyal kaydı ana thread dışında sessizce atlanır,
            # kapatma `SvcStop` → `self._runtime.stop()` üzerinden gelir).
            self._runtime_thread = threading.Thread(
                target=_run_runtime, name="agent-runtime", daemon=True
            )
            self._runtime_thread.start()

            win32event.WaitForSingleObject(self._stop_handle, win32event.INFINITE)
            if self._runtime_thread is not None:
                self._runtime_thread.join(timeout=10)
            logger.info("Servis durdu")

    return ITOpsAgentService


def main() -> None:
    """PyInstaller `packaging/windows/IT-Operations-Agent-Service.spec`
    build'inin entry point'i. SCM argümansız çağırır (`SvcDoRun`
    akışına girer); `install`/`remove`/`start`/`stop` gibi argümanlarla
    elle çağrılırsa pywin32'nin kendi komut satırı işleyicisine
    devredilir (kullanıcının `sc.exe` script'leri BUNU kullanmaz,
    yalnızca referans/manuel debug için)."""
    import sys

    servicemanager, _win32event, _win32service, win32serviceutil = _import_pywin32()
    service_class = _build_service_class()

    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(service_class)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(service_class)


if __name__ == "__main__":
    main()
