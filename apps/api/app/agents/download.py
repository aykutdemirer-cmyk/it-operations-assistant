"""Windows Agent EXE download — artifact çözümleme (Faz 32).

Build (PyInstaller, `apps/agent/packaging/windows/build.ps1`) ve
download (bu modül) BİLİNÇLİ olarak birbirinden ayrı: backend başlangıçta
veya bir request sırasında ASLA PyInstaller çalıştırmaz, yalnızca
build.ps1'in önceden ürettiği dosyaları okur.

Güvenlik: kullanıcıdan/istekten HİÇBİR path/dosya adı ALINMAZ — tek
kaynak `apps/agent/dist/build-info.json` (build.ps1 tarafından, sunucu
tarafında, önceden üretilir). Bu, path traversal'ı yapısal olarak
imkansız kılar (allowlist tek bir sabit dosya)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

# `apps/api/app/agents/download.py` -> parents[4] == repo kökü (bkz.
# `app/db/agents.py::_SCHEMA_SQL_PATH` ile aynı derinlik deseni).
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DIST_DIR = _REPO_ROOT / "apps" / "agent" / "dist"
_BUILD_INFO_PATH = _DIST_DIR / "build-info.json"

# `filename` alanı build-info.json'dan gelse bile (kullanıcıdan DEĞİL)
# savunma amaçlı ekstra bir doğrulama — yol ayırıcı/üst dizin referansı
# içermeyen, yalnızca beklenen desene uyan bir dosya adı kabul edilir.
_SAFE_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]+\.exe$")


@dataclass
class WindowsAgentArtifact:
    version: str
    filename: str
    size_bytes: int
    built_at: str
    path: Path


class ArtifactNotAvailableError(Exception):
    """`build-info.json` yok, bozuk, veya işaret ettiği EXE dosyası
    gerçekte mevcut değil — hepsi aynı dürüst "henüz build edilmemiş"
    durumuna denk gelir (bkz. `docs/decisions.md`)."""


def resolve_windows_agent_artifact() -> WindowsAgentArtifact:
    """Gerçek, önceden build edilmiş bir artifact'i çözer — hiçbir
    zaman bir dosya UYDURMAZ. `build-info.json` veya işaret ettiği EXE
    yoksa `ArtifactNotAvailableError` fırlatır (çağıran taraf bunu
    404'e çevirir)."""
    if not _BUILD_INFO_PATH.exists():
        raise ArtifactNotAvailableError("build-info.json bulunamadı — Windows Agent henüz build edilmemiş")

    try:
        # `utf-8-sig`: `build-info.json` PowerShell (Windows PowerShell
        # 5.1'in `-Encoding utf8`'i BOM EKLER) ile üretiliyor olabilir —
        # `utf-8-sig` BOM varsa şeffafça çıkarır, yoksa normal utf-8 gibi
        # davranır (bkz. `packaging/windows/build.ps1`'in kendi BOM'suz
        # yazma düzeltmesi — bu ikinci bir savunma katmanı).
        info = json.loads(_BUILD_INFO_PATH.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ArtifactNotAvailableError("build-info.json okunamadı/bozuk") from exc

    filename = info.get("filename")
    version = info.get("version")
    if not filename or not version:
        raise ArtifactNotAvailableError("build-info.json eksik alan içeriyor")
    if not _SAFE_FILENAME_PATTERN.match(filename):
        # Kullanıcıdan gelen bir girdi DEĞİL (bkz. modül docstring'i) —
        # yine de savunma amaçlı: beklenmeyen bir isim varsa güvenmek
        # yerine dürüstçe "mevcut değil" say.
        raise ArtifactNotAvailableError("build-info.json içindeki dosya adı beklenmeyen bir biçimde")

    exe_path = (_DIST_DIR / filename).resolve()
    # Çözülen yolun GERÇEKTEN dist dizini içinde kaldığını doğrula —
    # savunma amaçlı ikinci bir katman.
    if _DIST_DIR.resolve() not in exe_path.parents:
        raise ArtifactNotAvailableError("Çözülen artifact yolu beklenen dizinin dışında")
    if not exe_path.is_file():
        raise ArtifactNotAvailableError(f"build-info.json {filename}'i işaret ediyor ama dosya yok")

    return WindowsAgentArtifact(
        version=str(version),
        filename=filename,
        size_bytes=info.get("size_bytes") or exe_path.stat().st_size,
        built_at=info.get("built_at") or "",
        path=exe_path,
    )
