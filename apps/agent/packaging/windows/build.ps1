# IT Operations Assistant — Windows Agent EXE build script (Faz 32).
#
# Kullanım (herhangi bir dizinden):
#   powershell -File apps/agent/packaging/windows/build.ps1
#
# Önkoşul: `apps/agent/.venv` zaten kurulu ve `requirements.txt` +
# `packaging/windows/requirements-build.txt` yüklü olmalı:
#   cd apps/agent
#   python -m venv .venv
#   .venv\Scripts\pip install -r requirements.txt -r packaging\windows\requirements-build.txt
#
# Bu script YALNIZCA build eder — backend'e dokunmaz, deploy etmez.
# Çıktı: apps/agent/dist/IT-Operations-Agent-<version>.exe +
# apps/agent/dist/build-info.json (backend'in `GET /api/agents/
# download/windows` endpoint'i BU json'ı okur, PyInstaller'ı asla
# kendisi çalıştırmaz — build ve download bilinçli olarak ayrı).

$ErrorActionPreference = "Stop"

$PackagingDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AgentRoot = (Resolve-Path (Join-Path $PackagingDir "..\..")).Path
$VenvPython = Join-Path $AgentRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Sanal ortam bulunamadi: $VenvPython`nOnce sirasiyla calistirin:`n  cd apps/agent`n  python -m venv .venv`n  .venv\Scripts\pip install -r requirements.txt -r packaging\windows\requirements-build.txt"
    exit 1
}

# Agent versiyonunu TEK doğruluk kaynağından (agent/__init__.py) okur
# — bu script veya .spec dosyası içinde elle tekrar YAZILMAZ.
$Version = & $VenvPython -c "import sys; sys.path.insert(0, r'$AgentRoot'); from agent import __version__; print(__version__, end='')"
if ([string]::IsNullOrWhiteSpace($Version)) {
    Write-Error "Agent versiyonu okunamadi (agent/__init__.py::__version__)"
    exit 1
}
Write-Host "Agent versiyonu: $Version"

$DistPath = Join-Path $AgentRoot "dist"
$BuildPath = Join-Path $AgentRoot "build"
$SpecFile = Join-Path $PackagingDir "IT-Operations-Agent.spec"

Write-Host "PyInstaller build basliyor..."
& $VenvPython -m PyInstaller --distpath $DistPath --workpath $BuildPath --noconfirm $SpecFile

if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build basarisiz (exit code $LASTEXITCODE)"
    exit 1
}

$ExeName = "IT-Operations-Agent-$Version.exe"
$ExePath = Join-Path $DistPath $ExeName

if (-not (Test-Path $ExePath)) {
    Write-Error "Beklenen EXE bulunamadi: $ExePath"
    exit 1
}

$SizeBytes = (Get-Item $ExePath).Length
$BuiltAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")

$BuildInfo = [ordered]@{
    version    = $Version
    filename   = $ExeName
    size_bytes = $SizeBytes
    built_at   = $BuiltAt
}
# NOT: Windows PowerShell 5.1'de `Set-Content -Encoding utf8` bir BOM
# (byte order mark) EKLER — Python'un `json.loads()`'u bunu düz utf-8
# olarak kabul etmez (`Unexpected UTF-8 BOM` hatası). İçerik zaten saf
# ASCII (versiyon/dosya adı/ISO zaman damgası) olduğu için `-Encoding
# ascii` ile BOM sorunu tamamen ortadan kaldırılıyor (backend tarafında
# da `utf-8-sig` ile ikinci bir savunma katmanı var, bkz.
# app/agents/download.py).
$BuildInfoJsonPath = Join-Path $DistPath "build-info.json"
$BuildInfo | ConvertTo-Json | Set-Content -Path $BuildInfoJsonPath -Encoding ascii

Write-Host ""
Write-Host "Build tamamlandi:"
Write-Host "  EXE:  $ExePath ($([math]::Round($SizeBytes / 1MB, 1)) MB)"
Write-Host "  Info: $(Join-Path $DistPath 'build-info.json')"
Write-Host ""
Write-Host "Backend calisirken artik su adresten indirilebilir: GET /api/agents/download/windows"
