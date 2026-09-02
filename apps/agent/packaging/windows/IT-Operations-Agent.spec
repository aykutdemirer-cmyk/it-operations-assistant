# IT Operations Assistant — Windows Agent PyInstaller spec (Faz 32).
#
# Elle çalıştırılmaz — bkz. `build.ps1`. Tek-dosya (onefile) modu:
# `a.binaries`/`a.zipfiles`/`a.datas` doğrudan `EXE()`'e verilir (iki
# dosyalı `COLLECT` modu KULLANILMAZ).
#
# Versiyon TEK doğruluk kaynağından (`agent/__init__.py::__version__`)
# okunur — burada veya `build.ps1`'de elle tekrar YAZILMAZ.

import sys
from pathlib import Path

# PyInstaller spec dosyalarını `exec()` ile çalıştırırken `SPECPATH`
# adlı özel bir global enjekte eder (bu dosyanın bulunduğu dizin).
_PACKAGING_DIR = Path(SPECPATH)  # noqa: F821
_AGENT_ROOT = (_PACKAGING_DIR / ".." / "..").resolve()

sys.path.insert(0, str(_AGENT_ROOT))
from agent import __version__ as AGENT_VERSION  # noqa: E402

EXE_NAME = f"IT-Operations-Agent-{AGENT_VERSION}"

a = Analysis(  # noqa: F821
    [str(_AGENT_ROOT / "agent" / "__main__.py")],
    pathex=[str(_AGENT_ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[],
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
    name=EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    # `console=True` — bu bir CLI aracı (`start`/`status`/`inventory`/
    # `test-connection`/`version`), gizli bir arka plan süreci DEĞİL.
    # Kullanıcı `.exe`'yi çift tıklayınca bir terminal penceresi açılır
    # ve `start` komutunun canlı loglarını gösterir — bu BİLİNÇLİ bir
    # şeffaflık tercihi (Faz 32 §6 — "gizli izleme" YASAK ilkesiyle
    # tutarlı, agent ne yaptığını her zaman görünür şekilde loglar).
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
