"""Agent yapılandırması — ortam değişkenlerinden (veya bir `.env`
dosyasından) okunur. `python-dotenv` bağımlılığı KASITLI olarak
eklenmedi — format basit (`KEY=VALUE`, `#` yorum satırları) olduğu için
küçük bir stdlib-only loader yeterli (bkz. `_load_dotenv`).

Secret DEĞERİ (`AGENT_TOKEN`) hiçbir yerde loglanmaz — bkz. `__repr__`
ve `authentication.py::redact_token`."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_HEARTBEAT_INTERVAL = 30
_DEFAULT_TELEMETRY_INTERVAL = 30
_DEFAULT_INVENTORY_INTERVAL = 300
_DEFAULT_COMMAND_POLL_INTERVAL = 10
_DEFAULT_STATE_FILE = ".itops-agent-state.json"


class ConfigError(Exception):
    """Yapılandırma eksik/geçersiz (ör. `BACKEND_URL` verilmemiş)."""


@dataclass
class AgentConfig:
    backend_url: str
    agent_id: str | None = None
    agent_token: str | None = None
    # Faz 31 — self-service registration artık geçerli bir enrollment
    # kodu ister (bkz. docs/decisions.md). Bir credential DEĞİLDİR
    # (tek başına hiçbir kaynağa erişim vermez), bu yüzden `__repr__`'de
    # gizlenmesi gerekmez — yine de kullanıcı deneyimi için token'la
    # aynı satırda karışmasın diye ayrı tutulur.
    enrollment_code: str | None = None
    heartbeat_interval: int = _DEFAULT_HEARTBEAT_INTERVAL
    telemetry_interval: int = _DEFAULT_TELEMETRY_INTERVAL
    inventory_interval: int = _DEFAULT_INVENTORY_INTERVAL
    verify_tls: bool = True
    state_file: Path = field(default_factory=lambda: Path(_DEFAULT_STATE_FILE))
    max_processes_reported: int = 50
    # Faz 33 — Remote Command Execution. Varsayılan KAPALI (opt-in) —
    # backend'de bir process-kill/service-control komutu oluşsa bile,
    # bu makinenin agent'ı açıkça `ENABLE_REMOTE_COMMANDS=true` ile
    # etkinleştirilmemişse HİÇBİR komut çalıştırılmaz (bkz. docs/
    # decisions.md §17 — insan Auth/RBAC'tan önceki bilinen risk için
    # ek bir güvenlik katmanı).
    enable_remote_commands: bool = False
    command_poll_interval: int = _DEFAULT_COMMAND_POLL_INTERVAL

    def __repr__(self) -> str:  # pragma: no cover - yalnızca debug/log güvenliği
        token_display = "***" if self.agent_token else None
        return (
            f"AgentConfig(backend_url={self.backend_url!r}, agent_id={self.agent_id!r}, "
            f"agent_token={token_display!r}, enrollment_code={self.enrollment_code!r}, "
            f"heartbeat_interval={self.heartbeat_interval}, "
            f"telemetry_interval={self.telemetry_interval}, "
            f"inventory_interval={self.inventory_interval}, verify_tls={self.verify_tls})"
        )


def _load_dotenv(path: Path) -> None:
    """`.env` dosyasını `os.environ`'a yükler — YALNIZCA henüz
    ortamda TANIMLI OLMAYAN değişkenler için (gerçek ortam değişkenleri
    her zaman `.env`'e önceliklidir, `python-dotenv`'in varsayılan
    davranışıyla aynı)."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in ("false", "0", "no", "off")


def load_config(dotenv_path: Path | None = None) -> AgentConfig:
    """Yapılandırmayı ortam değişkenlerinden okur. `dotenv_path`
    verilmezse çalışma dizinindeki `.env` denenir (varsa)."""
    _load_dotenv(dotenv_path or Path(".env"))

    backend_url = os.environ.get("BACKEND_URL")
    if not backend_url:
        raise ConfigError("BACKEND_URL zorunlu — ör. http://10.0.213.5:8000")

    state_file_raw = os.environ.get("AGENT_STATE_FILE", _DEFAULT_STATE_FILE)

    return AgentConfig(
        backend_url=backend_url.rstrip("/"),
        agent_id=os.environ.get("AGENT_ID") or None,
        agent_token=os.environ.get("AGENT_TOKEN") or None,
        enrollment_code=os.environ.get("ENROLLMENT_CODE") or None,
        heartbeat_interval=_int_env("HEARTBEAT_INTERVAL", _DEFAULT_HEARTBEAT_INTERVAL),
        telemetry_interval=_int_env("TELEMETRY_INTERVAL", _DEFAULT_TELEMETRY_INTERVAL),
        inventory_interval=_int_env("INVENTORY_INTERVAL", _DEFAULT_INVENTORY_INTERVAL),
        verify_tls=_bool_env("VERIFY_TLS", True),
        state_file=Path(state_file_raw),
        max_processes_reported=_int_env("MAX_PROCESSES_REPORTED", 50),
        enable_remote_commands=_bool_env("ENABLE_REMOTE_COMMANDS", False),
        command_poll_interval=_int_env("COMMAND_POLL_INTERVAL", _DEFAULT_COMMAND_POLL_INTERVAL),
    )
