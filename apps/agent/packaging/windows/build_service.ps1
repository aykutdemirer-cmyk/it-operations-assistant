# IT Operations Assistant — Windows Service EXE build script.
#
# Kullanım (herhangi bir dizinden):
#   powershell -File apps/agent/packaging/windows/build_service.ps1
#
# `build.ps1`'den AYRI: bu, CLI EXE'sini DEĞİL, `IT-Operations-Agent-
# Service.spec`'i (agent/winservice.py giriş noktalı, SCM-uyumlu)
# build eder. Önkoşul aynı (`apps/agent/.venv` + `requirements.txt` +
# `packaging/windows/requirements-build.txt` — pywin32 dahil).
#
# Çıktı: apps/agent/dist/itops-agent.exe (SABİT ad — bkz. .spec
# dosyasının docstring'i) + apps/agent/dist/service-build-info.json
# (backend'in `GET /api/agents/download/windows-service/info`
# endpoint'inin okuduğu manifest — `build.ps1`'in kendi
# `build-info.json`'ıyla AYNI amaç, ayrı dosya). `agent/scripts/
# install_windows_service.ps1` bu script'i çağırır, sonra `sc.exe
# create` ile kaydeder.

$ErrorActionPreference = "Stop"

$PackagingDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AgentRoot = (Resolve-Path (Join-Path $PackagingDir "..\..")).Path
$VenvPython = Join-Path $AgentRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Sanal ortam bulunamadi: $VenvPython`nOnce sirasiyla calistirin:`n  cd apps/agent`n  python -m venv .venv`n  .venv\Scripts\pip install -r requirements.txt -r packaging\windows\requirements-build.txt"
    exit 1
}

$DistPath = Join-Path $AgentRoot "dist"
$BuildPath = Join-Path $AgentRoot "build"
$SpecFile = Join-Path $PackagingDir "IT-Operations-Agent-Service.spec"

Write-Host "Windows Servisi EXE build basliyor..."
& $VenvPython -m PyInstaller --distpath $DistPath --workpath $BuildPath --noconfirm $SpecFile

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build basarisiz (exit code $LASTEXITCODE)"
    exit 1
}

$ExePath = Join-Path $DistPath "itops-agent.exe"
if (-not (Test-Path $ExePath)) {
    Write-Error "Beklenen EXE bulunamadi: $ExePath"
    exit 1
}

$SizeBytes = (Get-Item $ExePath).Length

# Agent versiyonunu TEK doğruluk kaynağından (agent/__init__.py) okur —
# `build.ps1` ile aynı desen.
$Version = & $VenvPython -c "import sys; sys.path.insert(0, r'$AgentRoot'); from agent import __version__; print(__version__, end='')"
$BuiltAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

$BuildInfo = [ordered]@{
    version    = $Version
    filename   = "itops-agent.exe"
    size_bytes = $SizeBytes
    built_at   = $BuiltAt
}
# `build.ps1`'deki AYNI BOM sorunu için AYNI düzeltme: Windows
# PowerShell 5.1'de `-Encoding utf8` bir BOM ekler, Python'un
# `json.loads()`'unu bozar — içerik saf ASCII olduğu için `-Encoding
# ascii` kullanılıyor (backend tarafında `utf-8-sig` ile ikinci bir
# savunma katmanı da var, bkz. app/agents/download.py).
$BuildInfoJsonPath = Join-Path $DistPath "service-build-info.json"
$BuildInfo | ConvertTo-Json | Set-Content -Path $BuildInfoJsonPath -Encoding ascii

Write-Host ""
Write-Host "Build tamamlandi: $ExePath ($([math]::Round($SizeBytes / 1MB, 1)) MB)"
Write-Host "Manifest: $BuildInfoJsonPath"
