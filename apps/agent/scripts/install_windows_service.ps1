# IT Operations Assistant — Agent'ı Windows Servisi olarak kurar.
#
# Kullanım (Yönetici PowerShell'den, herhangi bir dizinden):
#   powershell -File apps/agent/scripts/install_windows_service.ps1
#
# İKİ modda çalışır (otomatik algılanır):
#   - Kaynak ağacı içinden (`apps/agent/scripts/...`): önce Agent'ı
#     build eder (`packaging/windows/build_service.ps1`), sonra kaydeder.
#   - Bağımsız bir indirme paketinden (Ayarlar > Agent Yapılandırması
#     > "Windows Servisi Paketi İndir" ile alınan ZIP'in içinden — bkz.
#     `app/agents/download.py::build_windows_service_bundle_zip`):
#     ÖNCEDEN BUILD EDİLMİŞ `itops-agent.exe`'yi (ZIP'te bu script'in
#     YANINDA gelir) DOĞRUDAN kullanır, build ADIMI ATLANIR (hedef
#     bilgisayarda Python/PyInstaller kurulu olması GEREKMEZ).
#
# Ne yapar:
#   1. Yönetici (Administrator) yetkisi kontrolü.
#   2. Zaten kayıtlıysa mevcut servisi durdurur/siler (idempotent
#      yeniden kurulum — EXE dosyası servis ÇALIŞIRKEN kilitli olduğu
#      için bu adım build'DEN ÖNCE gelir).
#   3. (Yalnızca kaynak ağacı modunda) `packaging/windows/
#      build_service.ps1` ile Agent'ı bağımsız bir EXE'ye build eder —
#      bu EXE `agent/winservice.py`'yi giriş noktası yapar (pywin32
#      tabanlı, Windows Service Control Manager protokolünü doğru
#      implemente eder; bkz. o modülün docstring'i — düz bir konsol
#      EXE'si `sc.exe`'den gerçek bir graceful-stop sinyali ALAMAZ).
#   4. `sc.exe create` ile servisi sisteme kaydeder:
#        Service Name:  ITOpsAgent
#        Display Name:  IT Operations Assistant Telemetry Agent
#        Startup Type:  Automatic (start= auto)
#   5. Servisi hemen başlatır (`sc start ITOpsAgent`).
#
# Önkoşul: EXE'nin bulunacağı dizinde (build'den/paket çıkartmadan
# ÖNCE, elle) bir `.env` dosyası — en azından `BACKEND_URL` ve (ilk
# kayıt için) `ENROLLMENT_CODE` gerekir (Ayarlar > Agent
# Yapılandırması'ndan üretilir). Servis, EXE'nin KENDİ dizinindeki
# `.env`'i okur (bkz. `agent/main.py::_default_dotenv_path`).
#
# Kaldırmak için: `uninstall_windows_service.ps1`.

$ErrorActionPreference = "Stop"

$ServiceName = "ITOpsAgent"
$DisplayName = "IT Operations Assistant Telemetry Agent"
$Description = "Collects and reports system telemetry/inventory to the IT Operations Assistant backend."

# --- 1. Yönetici yetkisi kontrolü ---
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Bu script Yönetici (Administrator) yetkisi gerektirir. PowerShell'i 'Yönetici olarak çalıştır' ile yeniden açıp tekrar deneyin."
    exit 1
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BuildServiceScript = Join-Path $ScriptDir "..\packaging\windows\build_service.ps1"
# Kaynak ağacı mı, yoksa bağımsız bir indirme paketi mi? — bkz. dosya
# üstü açıklama.
$IsSourceTree = Test-Path $BuildServiceScript

if ($IsSourceTree) {
    $AgentRoot = (Resolve-Path (Join-Path $ScriptDir "..")).Path
    $DistDir = Join-Path $AgentRoot "dist"
} else {
    # Bağımsız paket: script, itops-agent.exe ve .env AYNI dizinde
    # (bkz. build_windows_service_bundle_zip).
    $DistDir = $ScriptDir
}
$ExePath = Join-Path $DistDir "itops-agent.exe"
$EnvPath = Join-Path $DistDir ".env"

if (-not (Test-Path $EnvPath)) {
    Write-Warning "$EnvPath bulunamadi. Servis BACKEND_URL/ENROLLMENT_CODE olmadan baslayamaz."
    Write-Warning "Devam etmeden once bu script ile AYNI dizinde bir '.env' dosyasi olusturun (ornek: apps/agent/.env.example)."
}

# --- 2. Zaten kayitliysa once temizle (idempotent yeniden kurulum) ---
# BUILD'DEN ONCE yapilir: servis calisirken EXE dosyasi Windows
# tarafindan kilitlenir (PermissionError/Access denied) — build
# calisan eski surecin ustune yazamaz. Gercek bir yeniden kurulumda
# YAKALANDI.
$existing = sc.exe query $ServiceName 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "Mevcut '$ServiceName' servisi bulundu - once durdurulup kaldiriliyor..."
    sc.exe stop $ServiceName | Out-Null
    Start-Sleep -Seconds 2
    sc.exe delete $ServiceName | Out-Null
    Start-Sleep -Seconds 1
}

# --- 3. Build (yalnizca kaynak agacinda) ---
if ($IsSourceTree) {
    Write-Host "Agent EXE build ediliyor..."
    & $BuildServiceScript
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $ExePath)) {
        Write-Error "Build basarisiz oldu - EXE bulunamadi: $ExePath"
        exit 1
    }
} else {
    if (-not (Test-Path $ExePath)) {
        Write-Error "itops-agent.exe bulunamadi: $ExePath (bu dosya bu script'in yaninda olmali - indirme paketini eksiksiz cikarttiginizdan emin olun)"
        exit 1
    }
    Write-Host "Onceden build edilmis EXE kullaniliyor: $ExePath"
}

Write-Host "Servis kaydediliyor (sc.exe create)..."
$binPath = '"' + $ExePath + '"'
sc.exe create $ServiceName binPath= $binPath DisplayName= $DisplayName start= auto
if ($LASTEXITCODE -ne 0) {
    Write-Error "sc.exe create basarisiz oldu (exit code $LASTEXITCODE)"
    exit 1
}
sc.exe description $ServiceName $Description | Out-Null
# Coksa/donerse otomatik yeniden baslat — systemd tarafindaki Restart=always
# ile ayni ruh (bkz. install_linux_service.sh).
sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/5000/restart/5000 | Out-Null

Write-Host "Servis baslatiliyor (sc.exe start)..."
sc.exe start $ServiceName
if ($LASTEXITCODE -ne 0) {
    Write-Error "sc.exe start basarisiz oldu (exit code $LASTEXITCODE) - 'sc.exe query $ServiceName' ve '$DistDir\agent.log' ile inceleyin."
    exit 1
}

Write-Host ""
Write-Host "Kurulum tamamlandi. Durum: sc.exe query $ServiceName"
Write-Host "Loglar: $DistDir\agent.log"
