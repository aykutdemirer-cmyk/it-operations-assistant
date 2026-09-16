"""CLI giriş noktası + ana çalışma döngüsü.

`python -m agent <command>` ile çalıştırılır (bkz. `__main__.py`).
Komutlar: `start` (sürekli çalışan ana döngü — heartbeat/telemetry/
inventory üç ayrı arka plan thread'i), `status`, `inventory` (yerel
envanteri stdout'a yazar, backend'e GÖNDERMEZ), `test-connection`,
`version`.

Backend erişilemezse agent ÇÖKMEZ — her döngü kendi içinde exponential
backoff ile kontrollü retry yapar (bkz. `_Loop`, §15 kullanıcı
talimatı)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from agent import __version__
from agent.authentication import load_local_state, redact_token, save_local_state
from agent.client import (
    BackendAuthenticationError,
    BackendClient,
    BackendError,
    BackendServerError,
    BackendUnavailableError,
    BackendValidationError,
)
from agent import commands as remote_commands
from agent.collectors import network, system
from agent.collectors import windows_updates
from agent.config import DEFAULT_STATE_FILE_NAME, AgentConfig, ConfigError, load_config
from agent.heartbeat import build_heartbeat_payload
from agent.inventory import build_inventory_payload
from agent.platform import current_os
from agent.telemetry import build_telemetry_payload

logger = logging.getLogger("agent.main")

# Kontrollü, sonlu bir backoff — sonsuz agresif retry YOK (§15). Son
# değerde (60s) sabitlenir, oradan büyümeye devam etmez.
_BACKOFF_SCHEDULE = (2, 5, 10, 30, 60)


def _configure_stdio() -> None:
    """Windows'ta konsol kod sayfası (ör. `cp1252`) UTF-8 olmayabilir —
    Türkçe karakterler veya emoji (✅/❌) içeren `print()`/log çıktısı bu
    durumda `UnicodeEncodeError` ile ÇÖKER. `TextIOWrapper.reconfigure`
    ile stdout/stderr'i açıkça UTF-8'e zorluyoruz (Python 3.7+, stdlib,
    yeni bağımlılık gerekmez). Backend'e GERÇEKTEN gönderilen payload
    zaten her zaman `.encode("utf-8")` ile kodlanıyordu (bkz.
    `client.py`) — bu yalnızca YEREL konsol çıktısını düzeltir."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass  # stream yeniden yapılandırmayı desteklemiyor (ör. bazı test/pipe senaryoları)


def _configure_logging() -> None:
    _configure_stdio()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _default_log_file_path() -> Path:
    """Windows Servisi/systemd daemon olarak çalışırken (bkz. `agent/
    winservice.py`, `deploy/systemd/itops-agent.service`) konsol çıktısı
    ya hiç yok ya da kimse bakmıyor — `AGENT_LOG_FILE` açıkça
    verilmediğinde makul bir varsayılan: frozen bir EXE'de EXE'nin
    KENDİ dizini (CWD, servis bağlamında öngörülemez olabilir — bkz.
    `_default_dotenv_path` ile aynı gerekçe), dev modda çalışma dizini."""
    base = Path(sys.executable).resolve().parent if _is_frozen() else Path(".")
    return base / "agent.log"


def _add_file_logging(log_file: Path | None) -> None:
    """`cmd_start` (ve servis giriş noktası) tarafından, config
    yüklendikten SONRA çağrılır — uzun süre çalışan `start` komutu için
    boyut sınırlı (rotating, 5MB × 3 yedek) bir dosyaya HER ZAMAN da
    loglar; `_configure_logging`'in konsol handler'ı bunun YERİNE değil,
    YANINDA çalışmaya devam eder (interaktif kullanımda ikisi de
    görünür). Dosya yazılamıyorsa (izin/disk hatası) agent ÇÖKMEZ —
    yalnızca konsola bir uyarı loglanır, servis/daemon çalışmaya devam
    eder."""
    from logging.handlers import RotatingFileHandler

    path = log_file or _default_log_file_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logging.getLogger().addHandler(handler)
        logger.info("Dosya loglama etkin: %s", path)
    except OSError as exc:
        logger.warning("Dosya loglama başlatılamadı (%s) — yalnızca konsola loglanmaya devam ediliyor", exc)


def _is_frozen() -> bool:
    """PyInstaller onefile/onedir olarak paketlenmiş bir EXE içinde mi
    çalışıyoruz? (`sys.frozen`, PyInstaller'ın kendi resmi sözleşmesi —
    bkz. Faz 32 packaging)."""
    return bool(getattr(sys, "frozen", False))


def _is_interactive_console() -> bool:
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except Exception:
        return False


def _default_dotenv_path() -> Path:
    """Frozen bir EXE'de `.env`'i HER ZAMAN EXE'nin KENDİ dizininde
    arar/yazar — konsolun açıldığı çalışma dizini (CWD) Explorer'ın
    çift tıklama davranışına göre değişebilir; EXE'nin kendi dosya
    konumu çok daha öngörülebilir bir referans noktasıdır. Geliştirme
    modunda (`python -m agent`) mevcut davranış (CWD'deki `.env`)
    AYNEN korunur."""
    if _is_frozen():
        return Path(sys.executable).resolve().parent / ".env"
    return Path(".env")


def _default_state_file_path() -> Path:
    """`_default_dotenv_path` ile AYNI gerekçe — frozen bir EXE'de
    `AGENT_STATE_FILE` (agent_id/token) EXE'nin KENDİ dizininde
    tutulur. **Gerçek bir Windows Servisi kurulumunda YAKALANAN bir
    bug'ın düzeltmesi:** Windows Service Control Manager (SCM) bir
    servisi başlatırken süreç CWD'sini genellikle `C:\\Windows\\
    System32` yapar — eski göreli varsayılan (`.itops-agent-state.
    json`, CWD'ye göre) bu durumda oraya yazılıyordu, EXE'nin yanına
    DEĞİL; bu da servis her yeniden kaydedildiğinde/EXE taşındığında
    ESKİ, artık geçersiz bir token'ın okunup sessizce kimlik
    doğrulama hatası vermesine yol açıyordu. Dev modda (`python -m
    agent`) mevcut davranış (CWD'deki dosya) AYNEN korunur."""
    if _is_frozen():
        return Path(sys.executable).resolve().parent / DEFAULT_STATE_FILE_NAME
    return Path(DEFAULT_STATE_FILE_NAME)


def _pause_before_exit() -> None:
    """Yalnızca frozen (PyInstaller) EXE + GERÇEK bir konsolda çalışır
    — çift tıklamayla açılan bir pencerenin, kullanıcı hata mesajını
    OKUYAMADAN kapanmasını önler (gerçek bir kullanıcı bildirimiyle
    bulunan bir UX hatası: EXE hiçbir çıktı görülmeden hemen
    kapanıyordu). `python -m agent`/otomasyon/CI ortamında (frozen
    değil VEYA interaktif değil) hiçbir etkisi yok — stdin'i asla
    gereksiz yere bloklamaz."""
    if _is_frozen() and _is_interactive_console():
        try:
            input("\nDevam etmek için Enter'a basın...")
        except (EOFError, KeyboardInterrupt):
            pass


def _write_env_value(dotenv_path: Path, key: str, value: str) -> None:
    """`.env` dosyasına `KEY=VALUE` yazar — dosya zaten varsa aynı
    anahtarın ESKİ satırını değiştirir (çift satır BIRAKMAZ), yoksa
    dosyayı oluşturur."""
    existing_lines: list[str] = []
    if dotenv_path.exists():
        existing_lines = dotenv_path.read_text(encoding="utf-8").splitlines()
    filtered = [line for line in existing_lines if not line.strip().startswith(f"{key}=")]
    filtered.append(f"{key}={value}")
    dotenv_path.write_text("\n".join(filtered) + "\n", encoding="utf-8")


def _prompt_for_initial_setup() -> None:
    """Frozen bir EXE hiçbir yapılandırma olmadan (`.env` yok, ortam
    değişkeni yok) çift tıklamayla açıldığında kullanıcıdan DOĞRUDAN
    Backend URL + Enrollment Code ister — Faz 32 master prompt'unun
    asıl hedeflediği akış ("kullanıcı EXE'yi çalıştırır → Backend URL +
    Enrollment Code girer"). Girilen değerler bir sonraki çalıştırmalar
    için `.env`'e yazılır VE bu sürecin ortamına hemen yansıtılır —
    agent'ı yeniden başlatmaya gerek kalmaz."""
    print("=" * 60)
    print("IT Operations Assistant Agent — Ilk Kurulum")
    print("=" * 60)
    print()
    dotenv_path = _default_dotenv_path()
    try:
        backend_url = input("Backend URL (ornek: http://10.0.213.10:8000): ").strip()
        while not backend_url:
            backend_url = input("Backend URL bos olamaz, tekrar girin: ").strip()
        enrollment_code = input("Enrollment Code (Ayarlar > Agent Yapilandirmasi'ndan alin): ").strip()
    except (EOFError, KeyboardInterrupt):
        # `_pause_before_exit()` BURADA çağrılmaz — `main()` zaten bu
        # `SystemExit`'i yakalayıp TEK bir kez duraklatıyor; burada da
        # çağrılırsa kullanıcı "Enter'a basın" istemini İKİ KEZ görür
        # (gerçek EXE çalıştırmasıyla bulunan bir bug — bkz. Faz 32 bugfix).
        print("\nKurulum iptal edildi.")
        sys.exit(1)

    _write_env_value(dotenv_path, "BACKEND_URL", backend_url)
    os.environ["BACKEND_URL"] = backend_url
    if enrollment_code:
        _write_env_value(dotenv_path, "ENROLLMENT_CODE", enrollment_code)
        os.environ["ENROLLMENT_CODE"] = enrollment_code

    print(f"\nYapilandirma kaydedildi: {dotenv_path}")
    print()


def _prompt_for_enrollment_code() -> None:
    """`start` çalışırken `EnrollmentCodeMissingError` alındığında —
    (BACKEND_URL zaten biliniyor ama ENROLLMENT_CODE eksik) yalnızca
    kodu ister, tüm kurulumu tekrarlamaz."""
    dotenv_path = _default_dotenv_path()
    try:
        code = input("Enrollment Code (Ayarlar > Agent Yapilandirmasi'ndan alin): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nIptal edildi.")
        return
    if not code:
        return
    _write_env_value(dotenv_path, "ENROLLMENT_CODE", code)
    os.environ["ENROLLMENT_CODE"] = code


class EnrollmentCodeMissingError(Exception):
    """Yeni bir kayıt gerekiyor ama `.env`'de/CLI'de bir `ENROLLMENT_
    CODE` verilmemiş (Faz 31 — backend artık bunu zorunlu kılıyor).
    Zaten kayıtlı bir agent (`.env`'de `AGENT_ID`/`AGENT_TOKEN` VEYA
    yerel state dosyası) için bu hiç gerekmez."""


def _registration_payload(enrollment_code: str) -> dict:
    host_info = system.collect_host_info()
    os_info = system.collect_os_info()
    interfaces = network.collect_interfaces()
    primary = next(
        (i for i in interfaces if i["interface_type"] not in ("loopback", "docker", "virtual") and i["ip_address"]),
        None,
    )
    return {
        "hostname": host_info["hostname"],
        "fqdn": host_info["fqdn"],
        "os": current_os(),
        "os_version": os_info.get("version"),
        "architecture": os_info.get("architecture"),
        "agent_version": __version__,
        "local_ip": primary["ip_address"] if primary else None,
        "mac_address": primary["mac_address"] if primary else None,
        "capabilities": ["heartbeat", "telemetry", "inventory"],
        "enrollment_code": enrollment_code,
    }


def ensure_registered(config: AgentConfig, client: BackendClient) -> tuple[str, str]:
    """Öncelik sırası: `.env`'de açıkça verilmiş `AGENT_ID`/
    `AGENT_TOKEN` -> yerel state dosyası -> yeni kayıt (`POST /api/
    agents/register`, artık `ENROLLMENT_CODE` gerektirir — Faz 31).
    Yeni kayıt sonucu HER ZAMAN state dosyasına yazılır — aksi halde
    her yeniden başlatmada backend'de yeni bir "ghost" agent kaydı
    birikir. Zaten bilinen bir kimlik varsa enrollment kodu HİÇ
    gerekmez (kod yalnızca YENİ kayıtlar için, tek kullanımlıktır)."""
    if config.agent_id and config.agent_token:
        logger.info("Agent kimliği .env'den okundu (agent_id=%s)", config.agent_id)
        return config.agent_id, config.agent_token

    local_state = load_local_state(config.state_file)
    if local_state:
        logger.info("Agent kimliği yerel state dosyasından okundu (agent_id=%s)", local_state["agent_id"])
        return local_state["agent_id"], local_state["token"]

    if not config.enrollment_code:
        raise EnrollmentCodeMissingError(
            "Bilinen bir agent kimliği yok ve ENROLLMENT_CODE verilmemiş. "
            "Backend'in Settings > Agent Configuration bölümünden yeni bir kod üretip "
            "ENROLLMENT_CODE olarak ayarlayın."
        )

    logger.info("Bilinen bir agent kimliği yok — enrollment kodu ile yeni kayıt deneniyor")
    response = client.register(_registration_payload(config.enrollment_code))
    agent_id, token = response["agent_id"], response["token"]
    save_local_state(config.state_file, agent_id=agent_id, token=token)
    logger.info("Agent kaydedildi: agent_id=%s token=%s", agent_id, redact_token(token))
    return agent_id, token


class _Loop:
    """Bir arka plan döngüsü — sabit aralıkla `action()` çağırır.
    `BackendUnavailableError`/`BackendServerError`'da exponential
    backoff uygular; `BackendAuthenticationError`'da `on_auth_failure`
    çağrılıp döngü tamamen durur (token artık geçersiz, tekrar denemek
    anlamsız — insan müdahalesi/yeniden kayıt gerekir)."""

    def __init__(self, name: str, interval: int, action, stop_event: threading.Event, on_auth_failure):
        self.name = name
        self._interval = interval
        self._action = action
        self._stop_event = stop_event
        self._on_auth_failure = on_auth_failure

    def run(self) -> None:
        backoff_index = 0
        while not self._stop_event.is_set():
            try:
                self._action()
                backoff_index = 0
            except BackendAuthenticationError:
                logger.error("[%s] kimlik doğrulama başarısız — token geçersiz/iptal edilmiş", self.name)
                self._on_auth_failure()
                return
            except BackendValidationError as exc:
                logger.error("[%s] backend payload'ı reddetti: %s", self.name, exc)
            except (BackendUnavailableError, BackendServerError) as exc:
                delay = _BACKOFF_SCHEDULE[min(backoff_index, len(_BACKOFF_SCHEDULE) - 1)]
                logger.warning("[%s] backend'e ulaşılamadı (%s) — %ds sonra tekrar denenecek", self.name, exc, delay)
                backoff_index += 1
                if self._stop_event.wait(delay):
                    return
                continue
            except BackendError:
                logger.exception("[%s] beklenmeyen bir backend hatası", self.name)

            if self._stop_event.wait(self._interval):
                return


class AgentRuntime:
    """`start()` çağrıldığında: kimliği çözer/kaydolur, üç bağımsız
    döngüyü (`heartbeat`/`telemetry`/`inventory`) ayrı thread'lerde
    başlatır, SIGINT/SIGTERM alana kadar bekler."""

    def __init__(self, config: AgentConfig):
        self._config = config
        self._client = BackendClient(config.backend_url, verify_tls=config.verify_tls)
        self._stop_event = threading.Event()
        self._started_at = time.time()
        self._agent_id: str | None = None
        self._token: str | None = None

    def start(self) -> None:
        try:
            self._agent_id, self._token = ensure_registered(self._config, self._client)
        except Exception as exc:
            # Gerçek kullanıcı bildirimiyle bulunan bir hata: bir Windows
            # Servisi olarak çalışırken (bkz. `agent/winservice.py`)
            # `ensure_registered` içindeki HERHANGİ bir hata (enrollment
            # kodu süresi dolmuş/kullanılmış, backend erişilemez, ağ
            # hatası vb.) burada YAKALANMADAN önce agent.log'da SADECE
            # "enrollment kodu ile yeni kayıt deneniyor" satırı görünüp
            # süreç sessizce ölüyordu — thread'in kendi exception'ı
            # hiçbir yere loglanmıyordu (Windows Servisi'nde stderr
            # kimsenin görmediği bir yere gider). Artık gerçek hata HER
            # ZAMAN `agent.log`'a yazılır, ardından YENİDEN fırlatılır —
            # `cmd_start`'ın `EnrollmentCodeMissingError` özel işleme
            # mantığı ve `main()`'in genel hata yakalayıcısı (konsol
            # modunda) AYNEN çalışmaya devam eder.
            logger.error("Agent kaydı/kimlik doğrulama başarısız oldu, agent başlatılamıyor: %s", exc)
            raise
        logger.info(
            "Agent başlıyor: agent_id=%s backend=%s heartbeat=%ds telemetry=%ds inventory=%ds",
            self._agent_id,
            self._config.backend_url,
            self._config.heartbeat_interval,
            self._config.telemetry_interval,
            self._config.inventory_interval,
        )

        loops = [
            _Loop("heartbeat", self._config.heartbeat_interval, self._send_heartbeat, self._stop_event, self.stop),
            _Loop("telemetry", self._config.telemetry_interval, self._send_telemetry, self._stop_event, self.stop),
            _Loop("inventory", self._config.inventory_interval, self._send_inventory, self._stop_event, self.stop),
        ]
        if self._config.enable_remote_commands:
            # Faz 33 — YALNIZCA açıkça etkinleştirilmişse 4. bir thread
            # başlar. Kapalıyken bu döngü hiç var olmaz — backend'de bir
            # komut oluşsa bile bu agent'a hiç ulaşmaz/sorulmaz.
            loops.append(
                _Loop(
                    "commands", self._config.command_poll_interval,
                    self._poll_and_execute_commands, self._stop_event, self.stop,
                )
            )
        else:
            logger.info("Uzaktan komut çalıştırma KAPALI (ENABLE_REMOTE_COMMANDS=false)")
        if current_os() == "windows" and self._config.enable_windows_updates_scan:
            # Windows Update taraması — yalnızca Windows'ta anlamlı,
            # Linux'ta bu döngü hiç oluşmaz (`ENABLE_WINDOWS_UPDATES_
            # SCAN` config'i Linux'ta da var ama etkisizdir). COM
            # `Search()` çağrısı yavaş olabileceğinden (gerçek bir
            # Windows Update sunucusu isteği) uzun bir varsayılan
            # aralıkla (6 saat) AYRI bir thread'de çalışır — heartbeat/
            # telemetry'yi ASLA bloklamaz.
            loops.append(
                _Loop(
                    "windows-updates", self._config.windows_updates_interval,
                    self._send_windows_updates, self._stop_event, self.stop,
                )
            )
        elif current_os() == "windows":
            logger.info("Windows Update taraması KAPALI (ENABLE_WINDOWS_UPDATES_SCAN=false)")
        threads = [threading.Thread(target=loop.run, name=loop.name, daemon=True) for loop in loops]
        for t in threads:
            t.start()

        def _handle_signal(signum, frame):
            logger.info("Kapatma sinyali alındı (signum=%s), agent durduruluyor...", signum)
            self.stop()

        try:
            signal.signal(signal.SIGINT, _handle_signal)
            if hasattr(signal, "SIGTERM"):
                signal.signal(signal.SIGTERM, _handle_signal)
        except ValueError:
            # `signal.signal()` yalnızca ANA thread'de çağrılabilir —
            # bu, `start()` bir arka plan thread'inden çalıştırıldığında
            # olur (bkz. `agent/winservice.py`: Windows Service Control
            # Manager'ın kendi thread'i `SvcDoRun`'ı çağırır, agent
            # runtime'ı AYRI bir thread'de başlatılır). Bu durumda
            # kapatma SIGINT/SIGTERM'den DEĞİL, doğrudan `self.stop()`
            # çağrısından (bkz. `SvcStop`) gelir — sinyal kaydı
            # gerekmez, sessizce atlanır.
            logger.debug("Sinyal handler'ları ana thread dışında kaydedilemedi — stop() doğrudan çağrılacak")

        try:
            while not self._stop_event.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            self.stop()

        for t in threads:
            t.join(timeout=5)
        logger.info("Agent durdu")

    def stop(self) -> None:
        self._stop_event.set()

    def _send_heartbeat(self) -> None:
        # Debug/Logging iyileştirmesi: HTTP durum kodu artık AÇIKÇA
        # loglanıyor (bkz. `client.py::BackendClient.heartbeat` — tam
        # `HttpResponse` döner, önceden yalnızca body dönüp status
        # sessizce atılıyordu).
        response = self._client.heartbeat(self._token, build_heartbeat_payload(self._started_at))
        logger.info("Heartbeat gönderildi (HTTP %s)", response.status)

    def _send_telemetry(self) -> None:
        self._client.send_telemetry(self._token, self._agent_id, build_telemetry_payload())
        logger.info("Telemetry gönderildi")

    def _send_inventory(self) -> None:
        payload = build_inventory_payload(max_processes=self._config.max_processes_reported)
        self._client.send_inventory(self._token, self._agent_id, payload)
        logger.info("Inventory gönderildi")

    def _send_windows_updates(self) -> windows_updates.UpdateScanResult:
        """Windows Update taramasını çalıştırır ve sonucu backend'e
        gönderir; `UpdateScanResult`'ı ÇAĞIRANA döner — hem periyodik
        arka plan döngüsü (`_Loop`) hem de `CHECK_UPDATES` komutu
        (bkz. `_poll_and_execute_commands`) AYNI fonksiyonu kullanır,
        tarama mantığı tek bir yerde yaşar."""
        result = windows_updates.scan_pending_updates()
        payload = {
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "scan_method": result.scan_method,
            "is_admin": result.is_admin,
            "updates": [
                {
                    "kb_number": item.kb_number,
                    "title": item.title,
                    "description": item.description,
                    "size_bytes": item.size_bytes,
                }
                for item in result.updates
            ],
            "error": result.error,
        }
        self._client.send_windows_updates(self._token, self._agent_id, payload)
        logger.info(
            "Windows Update taraması gönderildi (method=%s, %d güncelleme, admin=%s)",
            result.scan_method, len(result.updates), result.is_admin,
        )
        return result

    def _poll_and_execute_commands(self) -> None:
        """Faz 33 — bekleyen komutları çeker, her birini çalıştırır,
        gerçek sonucu backend'e bildirir. Bir komuttaki hata diğerlerini
        durdurmaz (mevcut `_Loop`/inventory/telemetry deseniyle aynı
        ilke). `refresh_inventory` (Faz 33.1), `check_updates` VE
        `install_update` `agent/commands.py`'nin OS-komut
        dispatcher'ından GEÇMEZ — üçü de agent'ın kendi envanter/
        Windows Update mantığını doğrudan tetikleyen özel komut
        tipleri. `install_update`'in `target`i belirli bir KB numarası
        (ör. `"KB5001234"`) veya `"all"` — diğer ikisininki anlamsız,
        sabit `"inventory"`/`"self"`."""
        pending = self._client.get_pending_commands(self._token, self._agent_id)
        inventory_already_sent = False
        state_changed = False
        sessions_changed = False
        windows_updates_state_changed = False

        for command in pending:
            command_id = command["id"]
            command_type = command["command_type"]
            action = command["action"]
            try:
                if command_type == "refresh_inventory":
                    self._send_inventory()
                    inventory_already_sent = True
                    result = remote_commands.CommandResult(True, "Envanter tazelendi")
                elif command_type == "check_updates":
                    scan_result = self._send_windows_updates()
                    if scan_result.scan_method == "unavailable":
                        result = remote_commands.CommandResult(
                            False, scan_result.error or "Windows Update taraması yapılamadı"
                        )
                    else:
                        result = remote_commands.CommandResult(
                            True,
                            f"{len(scan_result.updates)} güncelleme bulundu ({scan_result.scan_method})",
                        )
                elif command_type == "install_update":
                    # `target`: belirli bir KB numarası (ör. "KB5001234")
                    # veya "all" (bekleyen TÜM güncellemeler — bkz.
                    # `windows_updates.py::install_updates`). Gerçekten
                    # indirip yükler — geri dönüşü olmayan, GERÇEK bir
                    # sistem değişikliği (bkz. frontend'in `ConfirmModal`
                    # zorunluluğu, `kill_process`/`service_control`/
                    # `power_control` ile AYNI ilke).
                    install_result = windows_updates.install_updates(command["target"])
                    result = remote_commands.CommandResult(install_result.success, install_result.detail)
                    windows_updates_state_changed = True
                else:
                    result = remote_commands.execute(
                        command_type, action, command["target"], backend_url=self._config.backend_url
                    )
                    if command_type in ("kill_process", "service_control"):
                        state_changed = True
                    elif command_type == "power_control" and action == "logoff":
                        # reboot/shutdown için envanter/telemetry
                        # tazelemenin ANLAMI YOK — makine zaten kapanıyor,
                        # agent birazdan ölecek. `logoff` ise SADECE
                        # oturum durumunu değiştirir (bkz. telemetry'deki
                        # `sessions`), süreç/servis listesini DEĞİŞTİRMEZ.
                        sessions_changed = True
            except Exception as exc:  # noqa: BLE001 - bir komutun beklenmeyen hatası döngüyü durdurmasın
                logger.exception("Komut çalıştırılırken beklenmeyen hata: %s", command_id)
                result = remote_commands.CommandResult(False, f"Beklenmeyen hata: {exc}")

            status = "succeeded" if result.success else "failed"
            logger.info("Komut işlendi: id=%s status=%s detail=%s", command_id, status, result.detail)
            self._client.report_command_result(self._token, self._agent_id, command_id, status, result.detail)

        if sessions_changed:
            try:
                self._send_telemetry()
            except Exception:
                logger.warning("Komut sonrası telemetry tazeleme başarısız oldu", exc_info=True)

        if state_changed and not inventory_already_sent:
            # Bir komut (kill/service control) çalıştırıldıktan sonra
            # UI'daki süreç/servis listesi normal `inventory_interval`
            # (varsayılan 300s) dolana kadar ESKİ kalırdı — kullanıcı
            # "durdurdum ama ekranda hâlâ çalışıyor görünüyor" bildirdi.
            # Düzeltme: en az bir kill/service komutu işlendiyse HEMEN
            # taze bir envanter gönderilir (zaten `refresh_inventory`
            # komutuyla bu turda gönderilmediyse — çift göndermeyi
            # önlemek için). Bu tazeleme başarısız olursa (ör. backend
            # geçici ulaşılamaz) komut sonuçları YİNE DE raporlanmış
            # olur — yalnızca burada loglanır, döngüyü durdurmaz.
            try:
                self._send_inventory()
            except Exception:
                logger.warning("Komut sonrası envanter tazeleme başarısız oldu", exc_info=True)

        if windows_updates_state_changed:
            # Bir `install_update` komutu işlendikten SONRA — başarılı da
            # olsa (yüklenen KB artık "bekleyen" listesinde görünmemeli)
            # başarısız da olsa (kullanıcı GÜNCEL `reboot_required`/hata
            # durumunu görmeli) — taze bir tarama gönderilir. `check_
            # updates` zaten kendi taramasını `_send_windows_updates()`
            # üzerinden gönderdiği için burada TEKRAR ÇAĞRILMAZ.
            try:
                self._send_windows_updates()
            except Exception:
                logger.warning("Komut sonrası Windows Update tazeleme başarısız oldu", exc_info=True)


def _warn_if_insecure_backend(config: AgentConfig) -> None:
    """Faz 31 — TLS sertleştirme notu. `BACKEND_URL` `http://` ise
    (production'da olmaması gereken bir durum) her başlatmada GÖRÜNÜR
    bir uyarı loglar. Bu bir SERT engelleme DEĞİLDİR (yerel geliştirme/
    test ortamında backend gerçekten HTTP çalışıyor olabilir) — yalnızca
    kullanıcıyı bilgilendirir. Sertifika doğrulaması global olarak
    ASLA kapatılmaz (bkz. `client.py::BackendClient`, yalnızca
    `VERIFY_TLS=false` açıkça verildiğinde, o çağrıya özgü bir
    `ssl.SSLContext` ile)."""
    if config.backend_url.startswith("http://"):
        logger.warning(
            "BACKEND_URL http:// kullanıyor (%s) — production'da HTTPS kullanılması ÖNERİLİR. "
            "Bu yalnızca bir uyarıdır, agent yine de çalışmaya devam eder.",
            config.backend_url,
        )


def _load_config_or_exit() -> AgentConfig:
    """`BACKEND_URL` yoksa VE frozen bir EXE + gerçek bir konsolda
    çalışıyorsak (çift tıklama senaryosu) kullanıcıdan DOĞRUDAN ister
    (bkz. `_prompt_for_initial_setup`) — bu, Faz 32'nin asıl hedeflediği
    "EXE'yi çalıştır, Backend URL + Enrollment Code gir" akışıdır.
    Değilse (dev modu veya otomasyon/CI) eski davranış aynen korunur:
    dürüst bir hata mesajı + çıkış. Pencerenin ERKEN kapanmaması için
    duraklatma BURADA değil, tek bir merkezi noktada — `main()`'de
    (bkz. orada `SystemExit`'i yakalayan try/except)."""
    dotenv_path = _default_dotenv_path()
    state_file_default = _default_state_file_path()
    try:
        config = load_config(dotenv_path=dotenv_path, default_state_file=state_file_default)
    except ConfigError as exc:
        if _is_frozen() and _is_interactive_console():
            _prompt_for_initial_setup()
            try:
                config = load_config(dotenv_path=dotenv_path, default_state_file=state_file_default)
            except ConfigError as exc2:
                _log_fatal_config_error(exc2)
                sys.exit(1)
        else:
            _log_fatal_config_error(exc)
            sys.exit(1)
    _warn_if_insecure_backend(config)
    return config


def _log_fatal_config_error(exc: ConfigError) -> None:
    """Ağ Bağlantı Sorunu — Debug/Logging iyileştirmesi: bir Windows
    Servisi/systemd daemon'u olarak (konsolsuz) çalışırken `BACKEND_URL`
    eksik/geçersizse önceden yalnızca stderr'e (kimsenin görmediği)
    yazılıyordu — GEÇERLİ bir konfigürasyon olmadığı için `config.
    log_file` de bilinmiyordu, `_add_file_logging` hiç çağrılmıyordu,
    `agent.log` dosyası bu durumda hiç OLUŞMUYORDU. Artık burada, `.env`
    içinde AÇIKÇA verilmiş bir `AGENT_LOG_FILE` varsa onu (elle
    `os.environ`'dan okunur — henüz geçerli bir `AgentConfig` yok),
    yoksa varsayılan konuma en azından BU FATAL hata dosyaya da
    yazılır. Dosyaya yazma kendisi başarısız olursa (izin/disk) agent
    yine de stderr'e yazıp çıkar — hiçbir ek exception fırlatmaz."""
    print(f"Yapılandırma hatası: {exc}", file=sys.stderr)
    log_file_env = os.environ.get("AGENT_LOG_FILE")
    _add_file_logging(Path(log_file_env) if log_file_env else None)
    logger.error("Agent başlatılamadı — yapılandırma hatası: %s", exc)


def cmd_start(_args: argparse.Namespace) -> int:
    _configure_logging()
    config = _load_config_or_exit()
    _add_file_logging(config.log_file)
    try:
        AgentRuntime(config).start()
    except EnrollmentCodeMissingError:
        if _is_frozen() and _is_interactive_console():
            _prompt_for_enrollment_code()
            config = _load_config_or_exit()
            try:
                AgentRuntime(config).start()
            except EnrollmentCodeMissingError as exc2:
                print(f"Yapılandırma hatası: {exc2}", file=sys.stderr)
                return 1
        else:
            print("Yapılandırma hatası: ENROLLMENT_CODE gerekli (Ayarlar > Agent Yapılandırması'ndan alın)", file=sys.stderr)
            return 1
    return 0


def cmd_status(_args: argparse.Namespace) -> int:
    _configure_logging()
    config = _load_config_or_exit()
    if config.agent_id and config.agent_token:
        print(f"Agent ID: {config.agent_id} (.env'den)")
        return 0
    local_state = load_local_state(config.state_file)
    if local_state:
        print(f"Agent ID: {local_state['agent_id']} (yerel state dosyasından)")
        return 0
    print("Agent henüz kayıtlı değil — `itops-agent start` ilk çalıştığında kaydolacak.")
    return 0


def cmd_inventory(_args: argparse.Namespace) -> int:
    """Yerel envanteri STDOUT'a yazar — backend'e GÖNDERMEZ (yalnızca
    yerel doğrulama/debug amaçlı, bkz. §41)."""
    _configure_logging()
    payload = build_inventory_payload()
    # `ensure_ascii=True` (varsayılan) BİLİNÇLİ olarak korunuyor — Windows'ta
    # stdout bir dosyaya yönlendirildiğinde konsol kod sayfası UTF-8
    # olmayabilir (`cp1254` vb.), niha `ensure_ascii=False` ile Türkçe
    # karakter içeren bir servis/process adı `UnicodeEncodeError`'a yol
    # açabilir. Backend'e GERÇEKTEN gönderilen payload (bkz. `client.py`)
    # her zaman `.encode("utf-8")` ile kodlanır, bu kısıtlamadan etkilenmez
    # — yalnızca bu yerel debug çıktısı ASCII-güvenli tutuluyor.
    print(json.dumps(payload, indent=2, default=str))
    return 0


def cmd_test_connection(_args: argparse.Namespace) -> int:
    _configure_logging()
    config = _load_config_or_exit()
    client = BackendClient(config.backend_url, verify_tls=config.verify_tls)

    try:
        client.test_connection()
    except BackendUnavailableError as exc:
        print(f"❌ Backend'e ulaşılamıyor: {exc}")
        return 1
    print("✅ Backend erişilebilir")

    try:
        agent_id, token = ensure_registered(config, client)
    except EnrollmentCodeMissingError as exc:
        print(f"❌ {exc}")
        return 1
    except BackendError as exc:
        print(f"❌ Kayıt/kimlik doğrulama başarısız: {exc}")
        return 1

    try:
        client.heartbeat(token, build_heartbeat_payload(time.time()))
    except BackendAuthenticationError:
        print("❌ Kimlik doğrulama geçersiz (token iptal edilmiş olabilir)")
        return 1
    except BackendError as exc:
        print(f"❌ Heartbeat başarısız: {exc}")
        return 1

    print(f"✅ Agent kayıtlı ve kimlik doğrulaması geçerli (agent_id={agent_id})")
    return 0


def cmd_version(_args: argparse.Namespace) -> int:
    print(__version__)
    return 0


_COMMANDS = {
    "start": cmd_start,
    "status": cmd_status,
    "inventory": cmd_inventory,
    "test-connection": cmd_test_connection,
    "version": cmd_version,
}


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="itops-agent", description="IT Operations Assistant — Agent")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("start", help="Agent'ı sürekli çalışan modda başlatır (foreground)")
    subparsers.add_parser("status", help="Bilinen agent kimliğini gösterir")
    subparsers.add_parser("inventory", help="Yerel envanteri stdout'a yazar (backend'e göndermez)")
    subparsers.add_parser("test-connection", help="Backend bağlantısını ve kimlik doğrulamasını test eder")
    subparsers.add_parser("version", help="Agent sürümünü gösterir")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Faz 32 — çift tıklamayla açılan bir EXE'ye argüman GEÇİRİLEMEZ
    (Windows Explorer hiçbir komut satırı argümanı eklemez) — argüman
    verilmemişse varsayılan olarak `start` çalıştırılır (gerçek bir
    kullanıcı bildirimiyle bulunan hata: önceden argparse "command
    required" hatası verip pencere ANINDA kapanıyordu). Herhangi bir
    hata/erken çıkışta (`SystemExit` dahil) frozen+interaktif bir
    konsolda pencere kapanmadan ÖNCE duraklatılır (`_pause_before_exit`)
    — tek, merkezi bir nokta, komutların kendi içinde tekrarlanmaz."""
    raw_args = sys.argv[1:] if argv is None else argv
    if not raw_args:
        raw_args = ["start"]

    exit_code = 1
    try:
        args = build_arg_parser().parse_args(raw_args)
        exit_code = _COMMANDS[args.command](args)
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else 1
    except Exception:
        # Frozen modda beklenmeyen bir hata da pencereyi ANINDA
        # kapatmasın diye burada yakalanıp loglanır. Dev modda
        # (`python -m agent`) tam traceback geliştirici için daha
        # değerli olduğundan YENİDEN fırlatılır.
        if _is_frozen():
            logger.exception("Beklenmeyen bir hata olustu")
            exit_code = 1
        else:
            raise

    if exit_code != 0:
        _pause_before_exit()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
