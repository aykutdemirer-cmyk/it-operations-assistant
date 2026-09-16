"""Faz 33 — backend'den gelen komutları GERÇEKTEN çalıştıran modül
(process kill / service start-stop-restart).

Güvenlik sınırları (bkz. docs/decisions.md §17):
- Bu modül YALNIZCA `AgentConfig.enable_remote_commands=True` ise hiç
  çağrılmaz (main.py'deki command-poll döngüsü varsayılan KAPALI
  başlar) — backend'de bir komut oluşsa bile, agent açıkça
  etkinleştirilmemişse çalıştırılmaz.
- Kritik süreç/servis KORUMASI (blacklist) burada, OTORİTER olarak
  uygulanır — backend hedef makinenin gerçek süreç/servis isimlerini
  BİLEMEZ, yalnızca kaba bir ön-kontrol yapar (ör. PID<=4).
- `subprocess.run` HER ZAMAN bir ARGÜMAN LİSTESİYLE çağrılır
  (`shell=True` YOK) — hedef PID/servis adı bir shell string'ine ASLA
  enjekte edilmez (command injection'a karşı yapısal koruma)."""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass

from agent.platform import current_os

logger = logging.getLogger("agent.commands")

# 0/4: Windows "System"/"System Idle Process" PID'leri. 1: Linux init/systemd.
_PROTECTED_PIDS = {0, 1, 4}

_PROTECTED_PROCESS_NAMES = {
    "system", "system idle process", "svchost.exe", "wininit.exe", "winlogon.exe",
    "csrss.exe", "smss.exe", "services.exe", "lsass.exe", "systemd", "init",
    "itops-agent", "itops-agent.exe", "it-operations-agent", "it-operations-agent.exe",
}

_PROTECTED_SERVICE_NAMES = {
    "rpcss", "dcomlaunch", "eventlog", "winmgmt", "samss", "lsm", "plugplay",
    "systemd", "networkmanager", "sshd", "dbus", "itops-agent",
}

_TIMEOUT_SECONDS = 15


@dataclass
class CommandResult:
    success: bool
    detail: str


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS, check=False)


def _process_output(result: subprocess.CompletedProcess) -> str:
    return (result.stderr or result.stdout or f"exit code {result.returncode}").strip()


def kill_process(pid: int) -> CommandResult:
    """Verilen PID'i sonlandırır. Blacklist kontrolünden geçemezse
    hiçbir OS komutu ÇALIŞTIRILMAZ."""
    if pid in _PROTECTED_PIDS:
        return CommandResult(False, f"PID {pid} korumalı bir sistem süreci — reddedildi")
    if pid == os.getpid():
        return CommandResult(False, "Agent kendi sürecini sonlandıramaz — reddedildi")

    try:
        import psutil

        proc_name = psutil.Process(pid).name().lower()
        if proc_name in _PROTECTED_PROCESS_NAMES:
            return CommandResult(False, f"'{proc_name}' korumalı bir süreç adı — reddedildi")
    except Exception:
        # Süreç zaten yok/erişilemiyor olabilir — blacklist kontrolü
        # atlanır, OS komutunun kendisi (taskkill/kill) zaten anlamlı
        # bir hata dönecektir (ör. "böyle bir süreç yok").
        pass

    try:
        if current_os() == "windows":
            result = _run(["taskkill", "/F", "/PID", str(pid)])
        else:
            result = _run(["kill", "-9", str(pid)])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CommandResult(False, f"Komut çalıştırılamadı: {exc}")

    if result.returncode == 0:
        return CommandResult(True, f"PID {pid} sonlandırıldı")
    return CommandResult(False, _process_output(result))


def control_service(service_name: str, action: str) -> CommandResult:
    """`action`: `start` | `stop` | `restart`."""
    normalized = service_name.strip()
    if not normalized:
        return CommandResult(False, "Servis adı boş olamaz")
    if normalized.lower() in _PROTECTED_SERVICE_NAMES:
        return CommandResult(False, f"'{normalized}' korumalı bir servis — reddedildi")
    if action not in ("start", "stop", "restart"):
        return CommandResult(False, f"Bilinmeyen aksiyon: {action}")

    try:
        if current_os() == "windows":
            return _control_service_windows(normalized, action)
        return _control_service_linux(normalized, action)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CommandResult(False, f"Komut çalıştırılamadı: {exc}")


_VERB_TR = {"start": "başlatıldı", "stop": "durduruldu", "restart": "yeniden başlatıldı"}


def _control_service_windows(name: str, action: str) -> CommandResult:
    if action == "restart":
        # `sc stop` servis zaten durmuşsa hata dönebilir — bu durumda
        # yine de `sc start`'a devam ederiz (asıl sonuç start'ın sonucu).
        _run(["sc", "stop", name])
        result = _run(["sc", "start", name])
    else:
        result = _run(["sc", action, name])

    if result.returncode == 0:
        return CommandResult(True, f"'{name}' {_VERB_TR[action]}")
    return CommandResult(False, _process_output(result))


def _control_service_linux(name: str, action: str) -> CommandResult:
    result = _run(["systemctl", action, name])
    if result.returncode == 0:
        return CommandResult(True, f"'{name}' {_VERB_TR[action]}")
    return CommandResult(False, _process_output(result))


_VERB_TR_POWER = {
    "reboot": "yeniden başlatma",
    "shutdown": "kapatma",
    "logoff": "oturum kapatma",
}

# Reboot/shutdown, GERÇEK `/t 0` (anında) DEĞİL, kısa bir gecikmeyle
# (saniye) çalıştırılır — BİLİNÇLİ bir sapma. `/t 0` ile OS komutu
# çalıştığı anda makine anında düşer; agent'ın kendisi de o anda ölür
# ve backend'e "başarılı" sonucunu HİÇBİR ZAMAN bildiremez — kullanıcı
# arayüzde sonsuza kadar "işleniyor" görür (dürüst ama yararsız bir
# UX). Kısa gecikme, `shutdown`/`systemctl` komutunun kendisinin HEMEN
# dönmesini (asıl kapanma/reboot arka planda, gecikmeden SONRA olur)
# ve agent'ın bu arada gerçek sonucu bildirebilmesini sağlar.
_POWER_DELAY_SECONDS = 3


def reboot() -> CommandResult:
    try:
        if current_os() == "windows":
            result = _run(["shutdown", "/r", "/t", str(_POWER_DELAY_SECONDS), "/f"])
        else:
            # `--no-block`: `systemctl reboot` komutunun kendisi HEMEN
            # döner (asıl reboot arka planda gerçekleşir) — agent'ın
            # sonucu bildirebilmesi için.
            result = _run(["systemctl", "reboot", "--no-block"])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CommandResult(False, f"Komut çalıştırılamadı: {exc}")
    if result.returncode == 0:
        return CommandResult(True, "Yeniden başlatma komutu gönderildi")
    return CommandResult(False, _process_output(result))


def shutdown() -> CommandResult:
    try:
        if current_os() == "windows":
            result = _run(["shutdown", "/s", "/t", str(_POWER_DELAY_SECONDS), "/f"])
        else:
            # `--no-block`: `systemctl poweroff` komutunun kendisi HEMEN
            # döner (asıl kapanma arka planda gerçekleşir) — agent'ın
            # sonucu bildirebilmesi için `reboot()` ile aynı gerekçe.
            result = _run(["systemctl", "poweroff", "--no-block"])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CommandResult(False, f"Komut çalıştırılamadı: {exc}")
    if result.returncode == 0:
        return CommandResult(True, "Kapatma komutu gönderildi")
    return CommandResult(False, _process_output(result))


def logoff(username: str | None) -> CommandResult:
    """Windows'ta `username` YOK SAYILIR — `logoff` yalnızca o anki
    (agent'ın çalıştığı) interaktif oturumu kapatır, Windows'un kendi
    `logoff` komutunun davranışı budur. Linux'ta `pkill -u` hedefli bir
    kullanıcı adı GEREKTİRİR — boşsa dürüstçe reddedilir, tahmini bir
    kullanıcıya ASLA düşülmez."""
    try:
        if current_os() == "windows":
            result = _run(["logoff"])
        else:
            normalized = (username or "").strip()
            if not normalized:
                return CommandResult(False, "Linux'ta oturum kapatma için kullanıcı adı gerekli")
            result = _run(["pkill", "-KILL", "-u", normalized])
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CommandResult(False, f"Komut çalıştırılamadı: {exc}")
    if result.returncode == 0:
        return CommandResult(True, "Oturum kapatma komutu gönderildi")
    return CommandResult(False, _process_output(result))


def control_power(action: str, target: str) -> CommandResult:
    """`action`: `reboot` | `shutdown` | `logoff`. `target`: yalnızca
    `logoff` için (Linux'ta hedef kullanıcı adı) anlamlıdır, diğer
    aksiyonlarda yok sayılır."""
    if action == "reboot":
        return reboot()
    if action == "shutdown":
        return shutdown()
    if action == "logoff":
        return logoff(target)
    return CommandResult(False, f"Bilinmeyen güç aksiyonu: {action!r}")


def execute(command_type: str, action: str, target: str, *, backend_url: str | None = None) -> CommandResult:
    """Backend'den gelen `{command_type, action, target}` üçlüsünü
    çalıştırır — `main.py`'nin command-poll döngüsündeki tek giriş
    noktası. `backend_url` yalnızca `update_self` için gerekli (yeni
    binary'nin indirileceği adres) — diğer komut tipleri yok sayar."""
    if command_type == "kill_process":
        try:
            pid = int(target)
        except ValueError:
            return CommandResult(False, f"Geçersiz PID: {target!r}")
        return kill_process(pid)
    if command_type == "service_control":
        return control_service(target, action)
    if command_type == "power_control":
        return control_power(action, target)
    if command_type == "uninstall_service":
        from agent import lifecycle

        return lifecycle.uninstall_service()
    if command_type == "update_self":
        from agent import lifecycle

        if not backend_url:
            return CommandResult(False, "backend_url bilinmiyor — güncelleme başlatılamadı")
        return lifecycle.update_self(backend_url)
    return CommandResult(False, f"Bilinmeyen komut tipi: {command_type!r}")
