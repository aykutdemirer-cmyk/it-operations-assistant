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

import io
import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

# `apps/api/app/agents/download.py` -> parents[4] == repo kökü (bkz.
# `app/db/agents.py::_SCHEMA_SQL_PATH` ile aynı derinlik deseni).
_REPO_ROOT = Path(__file__).resolve().parents[4]
_AGENT_ROOT = _REPO_ROOT / "apps" / "agent"
_DIST_DIR = _AGENT_ROOT / "dist"
_BUILD_INFO_PATH = _DIST_DIR / "build-info.json"

# Windows Servisi paketi — `packaging/windows/build_service.ps1`'in
# ürettiği ayrı manifest (bkz. o script'in docstring'i). `filename`
# burada HER ZAMAN sabit `itops-agent.exe`dir (servis `binPath`'i
# olarak kayıtlı olduğu için versiyonlu DEĞİL — bkz. `.spec` dosyası).
_SERVICE_BUILD_INFO_PATH = _DIST_DIR / "service-build-info.json"
_SCRIPTS_DIR = _AGENT_ROOT / "scripts"
_INSTALL_SCRIPT_PATH = _SCRIPTS_DIR / "install_windows_service.ps1"
_UNINSTALL_SCRIPT_PATH = _SCRIPTS_DIR / "uninstall_windows_service.ps1"

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


def resolve_windows_service_artifact() -> WindowsAgentArtifact:
    """`resolve_windows_agent_artifact` ile AYNI mantık, ayrı manifest
    (`service-build-info.json`) ve ayrı, SABİT dosya adı (`itops-
    agent.exe` — versiyonlu DEĞİL, bkz. modül üstü sabitlerin
    docstring'i). Kod tekrarını önlemek yerine bilinçli olarak AYRI
    tutuldu: iki artifact'in build/deploy döngüsü birbirinden bağımsız
    (biri CLI EXE, diğeri SCM-uyumlu servis EXE'si) — paylaşımlı bir
    soyutlama gelecekte ikisini yanlışlıkla karıştırma riski taşırdı."""
    if not _SERVICE_BUILD_INFO_PATH.exists():
        raise ArtifactNotAvailableError(
            "service-build-info.json bulunamadı — Windows Servisi paketi henüz build edilmemiş"
        )
    try:
        info = json.loads(_SERVICE_BUILD_INFO_PATH.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ArtifactNotAvailableError("service-build-info.json okunamadı/bozuk") from exc

    filename = info.get("filename")
    version = info.get("version")
    if not filename or not version:
        raise ArtifactNotAvailableError("service-build-info.json eksik alan içeriyor")
    if not _SAFE_FILENAME_PATTERN.match(filename):
        raise ArtifactNotAvailableError("service-build-info.json içindeki dosya adı beklenmeyen bir biçimde")

    exe_path = (_DIST_DIR / filename).resolve()
    if _DIST_DIR.resolve() not in exe_path.parents:
        raise ArtifactNotAvailableError("Çözülen artifact yolu beklenen dizinin dışında")
    if not exe_path.is_file():
        raise ArtifactNotAvailableError(f"service-build-info.json {filename}'i işaret ediyor ama dosya yok")

    return WindowsAgentArtifact(
        version=str(version),
        filename=filename,
        size_bytes=info.get("size_bytes") or exe_path.stat().st_size,
        built_at=info.get("built_at") or "",
        path=exe_path,
    )


def build_windows_service_bundle_zip(artifact: WindowsAgentArtifact) -> bytes:
    """Servis EXE'sini + kurulum/kaldırma PowerShell script'lerini TEK
    bir ZIP olarak, bellekte (diske hiç yazmadan) paketler — başka bir
    bilgisayara kopyalanıp `install_windows_service.ps1` Yönetici
    olarak çalıştırılabilsin diye. Script'ler bu repodan (build
    artifact'i DEĞİL, kaynak kod) okunur; ikisi de yoksa dürüstçe
    `ArtifactNotAvailableError` fırlatır."""
    if not _INSTALL_SCRIPT_PATH.is_file() or not _UNINSTALL_SCRIPT_PATH.is_file():
        raise ArtifactNotAvailableError("Kurulum script'leri bulunamadı")

    readme = f"""IT Operations Assistant Agent — Windows Servisi Kurulum Paketi
================================================================

Bu paket, agent'i baska bir Windows bilgisayara kalici bir servis
olarak kurmak icindir (ITOpsAgent servisi, bilgisayar her acildiginda
otomatik baslar).

1. Bu ZIP'i hedef bilgisayarda bir klasore cikartin (ornek:
   C:\\itops-agent\\).
2. AYNI klasorde bir ".env" dosyasi olusturun, icine:

       BACKEND_URL=<backend adresiniz, ornek http://10.0.213.30:8000>
       ENROLLMENT_CODE=<Ayarlar > Agent Yapilandirmasi'ndan uretilen kod>

3. PowerShell'i Yonetici (Administrator) olarak acin, bu klasore gidin
   ve calistirin:

       powershell -File install_windows_service.ps1

   Bu, "{artifact.filename}"'i ITOpsAgent adinda, otomatik baslayan
   bir Windows Servisi olarak kaydeder ve hemen baslatir.

Kaldirmak icin (yine Yonetici PowerShell'den):

       powershell -File uninstall_windows_service.ps1

Surum: {artifact.version}  |  Build: {artifact.built_at}
"""

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(artifact.path, arcname=artifact.filename)
        zf.write(_INSTALL_SCRIPT_PATH, arcname="install_windows_service.ps1")
        zf.write(_UNINSTALL_SCRIPT_PATH, arcname="uninstall_windows_service.ps1")
        zf.writestr("README.txt", readme)
    return buffer.getvalue()
