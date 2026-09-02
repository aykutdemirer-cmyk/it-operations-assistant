"""Windows Agent packaging dosyaları için "smoke" testleri (Faz 32).

GERÇEK bir PyInstaller build'i BURADA ÇALIŞTIRILMAZ — bu, birim test
paketi için çok ağır/yavaş bir işlem olurdu (~20s, PyInstaller kurulu
olmasını gerektirir). Gerçek build doğrulaması elle (`packaging/
windows/build.ps1`) ve E2E doğrulama sırasında yapılır (bkz.
`docs/roadmap.md` Faz 32). Bu testler yalnızca packaging dosyalarının
VAR olduğunu, doğru entry point'i işaret ettiğini ve versiyonun tek bir
doğruluk kaynağından geldiğini doğrular."""

from pathlib import Path

from agent import __version__

_AGENT_ROOT = Path(__file__).resolve().parents[1]
_PACKAGING_DIR = _AGENT_ROOT / "packaging" / "windows"


def test_build_script_exists():
    assert (_PACKAGING_DIR / "build.ps1").is_file()


def test_spec_file_exists():
    assert (_PACKAGING_DIR / "IT-Operations-Agent.spec").is_file()


def test_requirements_build_file_exists():
    assert (_PACKAGING_DIR / "requirements-build.txt").is_file()


def test_spec_file_references_the_real_entrypoint():
    """Spec dosyası `agent/__main__.py`'yi (gerçek CLI entry point,
    `main.py::main()`'i çağırır) işaret etmeli — ayrı, gölge bir
    entry point OLUŞTURULMADI."""
    content = (_PACKAGING_DIR / "IT-Operations-Agent.spec").read_text(encoding="utf-8")
    assert "__main__.py" in content


def test_spec_file_does_not_hardcode_a_version_string():
    """Versiyon TEK doğruluk kaynağından (`agent/__init__.py::
    __version__`) okunmalı — spec dosyasında elle yazılmış bir
    `"1.0.0"` gibi bir literal OLMAMALI (versiyon değiştiğinde iki
    yerde senkron tutma riskini önler)."""
    content = (_PACKAGING_DIR / "IT-Operations-Agent.spec").read_text(encoding="utf-8")
    assert f'"{__version__}"' not in content
    assert "from agent import __version__" in content


def test_build_script_does_not_hardcode_a_version_string():
    content = (_PACKAGING_DIR / "build.ps1").read_text(encoding="utf-8")
    assert f'"{__version__}"' not in content
    assert f"'{__version__}'" not in content


def test_build_script_writes_ascii_encoding_not_bom_utf8():
    """Regresyon testi — Windows PowerShell 5.1'de `Set-Content
    -Encoding utf8` bir BOM ekler ve backend'in `json.loads()`'unu
    bozar (gerçek build sırasında keşfedilip düzeltildi, bkz.
    docs/decisions.md). `build-info.json` içeriği zaten saf ASCII
    olduğu için `-Encoding ascii` kullanılmalı, `-Encoding utf8`
    KULLANILMAMALI."""
    content = (_PACKAGING_DIR / "build.ps1").read_text(encoding="utf-8")
    # Yorum satırları HARİÇ — açıklayıcı yorumun kendisi kaçınılan
    # `-Encoding utf8` deyimini örnek olarak içerebilir (nitekim içeriyor).
    code_lines = [line for line in content.splitlines() if not line.strip().startswith("#")]
    set_content_lines = [line for line in code_lines if "Set-Content" in line]
    assert set_content_lines, "build.ps1 içinde beklenen bir Set-Content çağrısı bulunamadı"
    assert any("-Encoding ascii" in line for line in set_content_lines)
    assert not any("-Encoding utf8" in line for line in set_content_lines)


def test_version_is_a_plausible_semver_string():
    parts = __version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)
