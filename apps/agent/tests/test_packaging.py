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


# --- Windows Servisi build/kurulum otomasyonu ---

_AGENT_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS_DIR = _AGENT_ROOT / "scripts"


def test_service_spec_file_exists():
    assert (_PACKAGING_DIR / "IT-Operations-Agent-Service.spec").is_file()


def test_service_spec_references_winservice_entrypoint():
    content = (_PACKAGING_DIR / "IT-Operations-Agent-Service.spec").read_text(encoding="utf-8")
    assert "winservice.py" in content


def test_service_spec_uses_a_stable_exe_name_not_versioned():
    """Servis `binPath`'i her build'de AYNI kalmalı — CLI EXE'nin
    aksine (`IT-Operations-Agent-<version>.exe`) versiyonlu bir ad
    KULLANILMAMALI (bkz. .spec dosyasının docstring'i)."""
    content = (_PACKAGING_DIR / "IT-Operations-Agent-Service.spec").read_text(encoding="utf-8")
    assert 'name="itops-agent"' in content
    assert f'"{__version__}"' not in content


def test_build_service_script_exists():
    assert (_PACKAGING_DIR / "build_service.ps1").is_file()


def test_windows_install_uninstall_scripts_exist():
    assert (_SCRIPTS_DIR / "install_windows_service.ps1").is_file()
    assert (_SCRIPTS_DIR / "uninstall_windows_service.ps1").is_file()


def test_linux_install_uninstall_scripts_exist():
    assert (_SCRIPTS_DIR / "install_linux_service.sh").is_file()
    assert (_SCRIPTS_DIR / "uninstall_linux_service.sh").is_file()


def test_windows_install_script_registers_the_exact_expected_service_identity():
    """Kullanıcı isteğiyle BİREBİR eşleşmeli: Service Name, Display
    Name, Startup Type (bkz. `agent/winservice.py`'deki AYNI sabitler
    — ikisi arasında tutarlılık da ayrıca test edilir)."""
    content = (_SCRIPTS_DIR / "install_windows_service.ps1").read_text(encoding="utf-8")
    assert 'sc.exe create $ServiceName' in content
    assert 'start= auto' in content
    assert '$ServiceName = "ITOpsAgent"' in content
    assert '$DisplayName = "IT Operations Assistant Telemetry Agent"' in content


def test_windows_uninstall_script_stops_and_deletes():
    content = (_SCRIPTS_DIR / "uninstall_windows_service.ps1").read_text(encoding="utf-8")
    assert "sc.exe stop" in content
    assert "sc.exe delete" in content


def test_linux_install_script_uses_the_expected_restart_policy():
    """Kullanıcı isteği: `Restart=always`, `RestartSec=5`."""
    content = (_SCRIPTS_DIR / "install_linux_service.sh").read_text(encoding="utf-8")
    assert "Restart=always" in content
    assert "RestartSec=5" in content
    assert "systemctl daemon-reload" in content
    assert "systemctl enable" in content


def test_reference_systemd_unit_matches_the_install_scripts_restart_policy():
    content = (_AGENT_ROOT / "deploy" / "systemd" / "itops-agent.service").read_text(encoding="utf-8")
    assert "Restart=always" in content
    assert "RestartSec=5" in content


def test_winservice_module_declares_the_exact_expected_service_identity():
    content = (_AGENT_ROOT / "agent" / "winservice.py").read_text(encoding="utf-8")
    assert '_svc_name_ = "ITOpsAgent"' in content
    assert '_svc_display_name_ = "IT Operations Assistant Telemetry Agent"' in content


# --- Regresyon: Windows PowerShell 5.1, BOM'suz bir .ps1 dosyasını
# UTF-8 yerine sistem ANSI codepage'iyle (ör. cp1252) okuyabiliyor — bu
# durumda em/en dash'in (U+2014/U+2013) UTF-8 baytları (ör. em dash'in
# son baytı 0x94) cp1252'de bir "akıllı tırnak" karakterine denk
# geliyor ve PowerShell BUNU bir string sonlandırıcı olarak kabul
# ediyor: `Write-Error "... — ..."` gibi bir satır GERÇEKTEN bozuk bir
# .ps1 dosyası üretiyor (gerçek `powershell -File` ile keşfedilip
# doğrulandı — bkz. bu fazın E2E notları). Yorumlarda (`#...`) bu SORUN
# DEĞİL (asla tokenize edilmez) — yalnızca gerçek string literal'lar
# (Write-Host/Write-Error/Write-Warning mesajları) etkileniyor.
_DANGEROUS_DASH_CHARS = ("—", "–")  # em dash, en dash


def test_windows_scripts_never_use_em_or_en_dash_inside_write_string_literals():
    for ps1_path in list(_SCRIPTS_DIR.glob("*.ps1")) + [
        _PACKAGING_DIR / "build.ps1",
        _PACKAGING_DIR / "build_service.ps1",
    ]:
        content = ps1_path.read_text(encoding="utf-8")
        for line_no, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if not stripped.startswith(("Write-Host", "Write-Error", "Write-Warning")):
                continue
            for ch in _DANGEROUS_DASH_CHARS:
                assert ch not in line, (
                    f"{ps1_path.name}:{line_no} bir Write-* string literal'inde "
                    f"em/en dash içeriyor — PowerShell 5.1 + BOM'suz dosyada string'i "
                    f"erken sonlandırabilir (bkz. test docstring'i). ASCII tire (-) kullanın."
                )
