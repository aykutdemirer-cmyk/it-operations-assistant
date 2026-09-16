"""Agent Lifecycle Management — Uzaktan Silme (servis kaldırma) ve
Uzaktan Sürüm Güncelleme (Over-The-Air Update) mekanizmaları.

Windows-ONLY: pywin32 tabanlı Windows Servisi (`agent/winservice.py`)
yalnızca Windows'ta var — Linux'ta systemd servis hesabının kendi
kendini silme/güncelleme yetkisi güvenilir şekilde garanti edilemez,
bu yüzden ikisi de Linux'ta dürüstçe "desteklenmiyor" sonucu döner
(sessizce başarılı GÖSTERİLMEZ).

`update_self` çalışan EXE dosyasının KENDİSİNİ değiştiremez (Windows
dosya kilidi — süreç kendi binary'sini üzerine yazamaz) — bu yüzden
tamamen AYRI, DETACHED bir PowerShell yardımcı süreci üretir: bu süreç
agent'ın/servisin durmasını bekler, dosyayı değiştirir, servisi
yeniden başlatır. Agent kendisi yalnızca "güncelleme süreci
başlatıldı" sonucunu bildirebilir — gerçek swap'ın sonucunu KENDİ
süreci asla göremez (o sırada zaten durmuş olur), bu dürüstçe
`result_detail` metninde belirtilir."""

from __future__ import annotations

import io
import logging
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from agent.commands import CommandResult
from agent.platform import current_os

logger = logging.getLogger("agent.lifecycle")

_SERVICE_NAME = "ITOpsAgent"
_TIMEOUT_SECONDS = 15
_DOWNLOAD_TIMEOUT_SECONDS = 120


def uninstall_service() -> CommandResult:
    """Servisi durdurur ve SCM kaydını siler (`sc.exe delete`).
    EXE/dosyalar diskte KALIR — yalnızca servis kaydı kaldırılır (bir
    dosya silme işlemi, çalışan bir sürecin kendi EXE'sini silmesi
    Windows'ta zaten mümkün değildir)."""
    if current_os() != "windows":
        return CommandResult(False, "Servis kaldırma yalnızca Windows'ta destekleniyor")

    try:
        subprocess.run(
            ["sc", "stop", _SERVICE_NAME], capture_output=True, text=True, timeout=_TIMEOUT_SECONDS, check=False
        )
        result = subprocess.run(
            ["sc", "delete", _SERVICE_NAME], capture_output=True, text=True, timeout=_TIMEOUT_SECONDS, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CommandResult(False, f"Komut çalıştırılamadı: {exc}")

    if result.returncode == 0:
        return CommandResult(True, "Servis kaldırma komutu gönderildi — servis birazdan silinecek")
    return CommandResult(False, (result.stderr or result.stdout or f"exit code {result.returncode}").strip())


def _extract_exe_from_service_bundle_zip(zip_bytes: bytes, dest_dir: Path) -> Path:
    """`GET /api/agents/download/windows-service` bir ZIP döner (exe +
    kurulum script'leri + README — bkz. backend `app/agents/download.py
    ::build_windows_service_bundle_zip`); burada yalnızca `.exe` üyesi
    çıkarılır, script/README dosyaları YOK SAYILIR."""
    dest = dest_dir / "itops-agent.new.exe"
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        exe_names = [name for name in zf.namelist() if name.lower().endswith(".exe")]
        if not exe_names:
            raise ValueError("ZIP paketi içinde .exe dosyası bulunamadı")
        with zf.open(exe_names[0]) as source, open(dest, "wb") as target:
            target.write(source.read())
    return dest


def update_self(backend_url: str) -> CommandResult:
    """`backend_url` + `/api/agents/download/windows-service`'den
    güncel servis paketini indirir, EXE'yi çıkarır, bir DETACHED
    PowerShell yardımcı süreci ile swap+restart işlemini tetikler."""
    if current_os() != "windows":
        return CommandResult(False, "Uzaktan güncelleme yalnızca Windows'ta destekleniyor")
    if not getattr(sys, "frozen", False):
        return CommandResult(False, "Uzaktan güncelleme yalnızca paketlenmiş (frozen) EXE'de desteklenir")

    exe_path = Path(sys.executable).resolve()
    download_url = backend_url.rstrip("/") + "/api/agents/download/windows-service"

    try:
        with urllib.request.urlopen(download_url, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as response:
            zip_bytes = response.read()
        new_exe_path = _extract_exe_from_service_bundle_zip(zip_bytes, exe_path.parent)
    except Exception as exc:  # noqa: BLE001 - indirme/paket hatası dürüstçe rapor edilir
        return CommandResult(False, f"Yeni sürüm indirilemedi: {exc}")

    try:
        _spawn_update_helper(exe_path, new_exe_path)
    except OSError as exc:
        return CommandResult(False, f"Güncelleme yardımcı süreci başlatılamadı: {exc}")

    return CommandResult(
        True, "Güncelleme süreci başlatıldı — servis kısa süre içinde yeni sürümle yeniden başlayacak"
    )


def _spawn_update_helper(exe_path: Path, new_exe_path: Path) -> None:
    """Agent'ın/servisin durmasını bekleyip dosyayı değiştiren, agent
    sürecinden TAMAMEN bağımsız (DETACHED) bir PowerShell süreci
    başlatır — agent kendi EXE dosyasını KENDİSİ değiştiremez (Windows
    dosya kilidi, çalışan bir binary üzerine yazılamaz)."""
    script = (
        "Start-Sleep -Seconds 5\n"
        f"sc.exe stop {_SERVICE_NAME}\n"
        "Start-Sleep -Seconds 2\n"
        f"Copy-Item -Path '{new_exe_path}' -Destination '{exe_path}' -Force\n"
        f"Remove-Item -Path '{new_exe_path}' -Force -ErrorAction SilentlyContinue\n"
        f"sc.exe start {_SERVICE_NAME}\n"
    )
    script_path = Path(tempfile.gettempdir()) / "itops-agent-update.ps1"
    # ASCII: script içinde kullanıcıdan gelen/değişken bir metin yok
    # (yalnızca sabit servis adı + dosya yolları), em-dash/Türkçe
    # karakter riski taşımaz — yine de bilinçli olarak ASCII (bkz.
    # `packaging/windows/build.ps1`'in em-dash/BOM sorunlarıyla ilgili
    # gerçek bug geçmişi, `docs/decisions.md`).
    script_path.write_text(script, encoding="ascii")

    creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
        creationflags=creationflags,
        close_fds=True,
    )
