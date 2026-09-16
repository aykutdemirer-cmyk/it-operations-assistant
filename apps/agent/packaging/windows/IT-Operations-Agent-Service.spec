# IT Operations Assistant — Windows Service EXE PyInstaller spec.
#
# `IT-Operations-Agent.spec`'ten (interaktif CLI, `agent/__main__.py`)
# AYRI: bu EXE `agent/winservice.py::main`'i giriş noktası yapar —
# Windows Service Control Manager (SCM) protokolünü doğru implemente
# eder (bkz. `agent/winservice.py` docstring'i — düz bir konsol EXE'si
# `sc.exe`'den gerçek bir graceful-stop sinyali ALAMAZ). Elle
# çalıştırılmaz — bkz. `build_service.ps1`.
#
# Çıktı dosya adı BİLİNÇLİ olarak SABİT (`itops-agent`, versiyonsuz) —
# CLI EXE'nin aksine (`IT-Operations-Agent-<version>.exe`, `GET /api/
# agents/download/windows` tarafından servis edilir) bu EXE bir Windows
# Servisi'nin `binPath`'i olarak kayıtlıdır; servis her güncellemede
# `sc delete`/`sc create` ile yeniden kaydedilmek ZORUNDA kalmasın diye
# yolu her build'de AYNI kalır (bkz. `install_windows_service.ps1`).

import sys
from pathlib import Path

_PACKAGING_DIR = Path(SPECPATH)  # noqa: F821
_AGENT_ROOT = (_PACKAGING_DIR / ".." / "..").resolve()

sys.path.insert(0, str(_AGENT_ROOT))

a = Analysis(  # noqa: F821
    [str(_AGENT_ROOT / "agent" / "winservice.py")],
    pathex=[str(_AGENT_ROOT)],
    binaries=[],
    datas=[],
    # pywin32'nin servis dispatcher'ı bu modülleri dinamik olarak
    # kullanır — PyInstaller'ın statik analizi bazılarını kaçırabilir,
    # bu yüzden açıkça listeleniyor (bilinen bir pywin32+PyInstaller
    # gereksinimi).
    hiddenimports=["win32timezone", "servicemanager", "win32serviceutil"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="itops-agent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    # `console=False` — bu bir arka plan Windows Servisi, kullanıcıya
    # görünen bir terminal penceresi AÇMAMALI (SCM zaten Session 0'da,
    # izole bir ortamda çalıştırır; interaktif çift-tıklama akışı
    # `IT-Operations-Agent.spec`'in kendi CLI EXE'sindedir).
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
