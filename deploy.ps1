# deploy.ps1  -  IT Operations Assistant'ı sıfır bir Windows Server
# makinesinde bağımsız olarak ayağa kaldırır.
#
# Kullanım (Yönetici PowerShell'den):  .\deploy.ps1
#
# Ne yapar / ne yapmaz:
#  - WSL2 + Docker Desktop'ın kurulu olup olmadığını kontrol eder;
#    eksikse WSL2'yi `wsl --install` ile kurmayı DENER (yeniden başlatma
#    gerektirebilir  -  script bunu algılayıp kullanıcıyı bilgilendirir),
#    Docker Desktop'ı ise GUI kurulum gerektirdiği için OTOMATİK
#    KURMAZ  -  resmi indirme bağlantısını verir (sessiz/headless kurulum
#    Windows Server'da güvenilir değil, bkz. DEPLOYMENT.md §2).
#  - Windows Firewall'da 80/443/8000/4822 portlarını açar.
#  - Kök `.env.example`'dan gerçek bir `.env` üretir (rastgele, güçlü
#    sırlarla)  -  `.env` ZATEN VARSA dokunmaz.
#  - "Migrasyon" adımı YOK  -  deploy.sh ile AYNI gerekçe: şema `api`
#    servisi tarafından kendiliğinden uygulanır (`infra/postgres/
#    init.sql`, Alembic/ORM KULLANILMIYOR).
#  - Varsayılan Admin parolasını "admin123" gibi tahmin edilebilir
#    SABİTLEMEZ  -  rastgele üretip bir kez ekrana yazar.

#Requires -RunAsAdministrator

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

function Write-Step($msg)  { Write-Host "[deploy] $msg" -ForegroundColor Cyan }
function Write-Warn2($msg) { Write-Host "[deploy] $msg" -ForegroundColor Yellow }
function Write-Err2($msg)  { Write-Host "[deploy] $msg" -ForegroundColor Red }

# ---- 1. WSL2 kontrolü ------------------------------------------------

$wslInstalled = $null -ne (Get-Command wsl.exe -ErrorAction SilentlyContinue)
if (-not $wslInstalled) {
    Write-Step "WSL bulunamadı, 'wsl --install' ile kuruluyor (yeniden başlatma gerekebilir)..."
    wsl --install
    Write-Warn2 "WSL2 kuruldu/güncellendi. Bu makineyi YENİDEN BAŞLATIP script'i tekrar çalıştırın."
    exit 0
} else {
    Write-Step "WSL zaten kurulu."
}

# ---- 2. Docker kontrolü ----------------------------------------------

$dockerInstalled = $null -ne (Get-Command docker -ErrorAction SilentlyContinue)
if (-not $dockerInstalled) {
    Write-Err2 "Docker bulunamadı. Windows Server'da Docker Desktop'ın sessiz/otomatik kurulumu güvenilir değil  -  lütfen şu adımları izleyin:"
    Write-Host "  1. https://www.docker.com/products/docker-desktop adresinden 'Docker Desktop Installer.exe' indirin"
    Write-Host "  2. Kurulumu çalıştırın, 'Use WSL 2 instead of Hyper-V' seçili kalsın"
    Write-Host "  3. Docker Desktop'ı başlatıp bu script'i tekrar çalıştırın"
    Write-Host ""
    Write-Warn2 "Alternatif: sunucu sanal makinesiyse (vSphere/Hyper-V), önce host tarafında nested virtualization AÇIK olmalı (bkz. DEPLOYMENT.md §2  -  bu projede gerçek bir kurulumda karşılaşılmış bir engel)."
    exit 1
} else {
    Write-Step "Docker zaten kurulu ($(docker --version))."
}

try {
    docker info | Out-Null
} catch {
    Write-Err2 "Docker kurulu ama çalışmıyor gibi görünüyor. Docker Desktop'ı başlatıp tekrar deneyin."
    exit 1
}

$composeCmd = "docker compose"
try {
    docker compose version | Out-Null
} catch {
    Write-Err2 "'docker compose' bulunamadı  -  Docker Desktop güncel bir sürüm değil olabilir."
    exit 1
}

# ---- 3. Windows Firewall kuralları ------------------------------------

Write-Step "Windows Firewall kuralları kontrol ediliyor (80/443/8000/4822)..."
$rules = @(
    @{ Name = "ITOps-Web-HTTP";  Port = 80 },
    @{ Name = "ITOps-Web-HTTPS"; Port = 443 },
    @{ Name = "ITOps-API";       Port = 8000 },
    @{ Name = "ITOps-Guacd";     Port = 4822 }
)
foreach ($rule in $rules) {
    if (-not (Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $rule.Name -Direction Inbound -Protocol TCP `
            -LocalPort $rule.Port -Action Allow | Out-Null
        Write-Step "  Açıldı: $($rule.Name) (TCP $($rule.Port))"
    } else {
        Write-Step "  Zaten var: $($rule.Name)"
    }
}

# ---- 4. .env üretimi (idempotent) -------------------------------------

function New-RandomSecret([int]$Bytes = 48) {
    $buffer = New-Object byte[] $Bytes
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($buffer)
    $encoded = [Convert]::ToBase64String($buffer) -replace '[+/=]', ''
    return $encoded.Substring(0, [Math]::Min(48, $encoded.Length))
}

function New-FernetKey {
    # Fernet anahtarı: 32 ham baytın url-safe base64'ü.
    $buffer = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($buffer)
    return [Convert]::ToBase64String($buffer) -replace '\+', '-' -replace '/', '_'
}

if (Test-Path ".env") {
    Write-Step ".env zaten var  -  dokunulmadı (mevcut sırlar korunuyor)."
} else {
    Write-Step ".env üretiliyor (.env.example temel alınarak, rastgele sırlarla)..."
    Copy-Item ".env.example" ".env"

    $pgPassword  = New-RandomSecret
    $jwtSecret   = New-RandomSecret
    $fernetKey   = New-FernetKey
    $adminPass   = (New-RandomSecret 20)

    $content = Get-Content ".env"
    $content = $content -replace '^POSTGRES_PASSWORD=.*', "POSTGRES_PASSWORD=$pgPassword"
    $content = $content -replace '^JWT_SECRET_KEY=.*', "JWT_SECRET_KEY=$jwtSecret"
    $content = $content -replace '^PAM_VAULT_SECRET_KEY=.*', "PAM_VAULT_SECRET_KEY=$fernetKey"
    $content = $content -replace '^BOOTSTRAP_ADMIN_PASSWORD=.*', "BOOTSTRAP_ADMIN_PASSWORD=$adminPass"
    Set-Content -Path ".env" -Value $content -Encoding ascii

    Write-Host ""
    Write-Step "Üretilen İLK ADMIN parolası (yalnızca bu makinenin ilk açılışında geçerli, BİR DAHA GÖSTERİLMEYECEK):"
    Write-Host "    kullanıcı adı: admin"
    Write-Host "    parola:        $adminPass"
    Write-Host ""
    Write-Warn2 "Bu parolayı şimdi güvenli bir yere kaydedin. İlk girişten sonra .env'deki BOOTSTRAP_ADMIN_PASSWORD satırını silmeniz önerilir (bkz. DEPLOYMENT.md)."
}

# ---- 5. Kalıcı veri dizinleri -------------------------------------------

New-Item -ItemType Directory -Force -Path "data\pam-recordings" | Out-Null
New-Item -ItemType Directory -Force -Path "data\pam-drives" | Out-Null
Write-Step "Kalıcı veri dizinleri hazır: .\data\pam-recordings, .\data\pam-drives"

# ---- 6. Build + başlat ---------------------------------------------------

Write-Step "Servisler build edilip başlatılıyor (ilk çalıştırmada birkaç dakika sürebilir)..."
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { Write-Err2 "docker compose up başarısız oldu."; exit 1 }

Write-Step "Backend'in şemayı kurup sağlıklı olması bekleniyor..."
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "http://localhost:8000/api/health" -UseBasicParsing -TimeoutSec 3
        if ($resp.StatusCode -eq 200) { $ready = $true; break }
    } catch { Start-Sleep -Seconds 2 }
}
if ($ready) { Write-Step "Backend hazır: http://localhost:8000/api/health" }
else { Write-Warn2 "Backend henüz yanıt vermiyor  -  'docker compose logs -f api' ile kontrol edin." }

$webPort = (Get-Content ".env" | Where-Object { $_ -match '^WEB_HTTP_PORT=' }) -replace 'WEB_HTTP_PORT=', ''
if (-not $webPort) { $webPort = "80" }

Write-Host ""
Write-Step "Kurulum tamamlandı."
Write-Host "  Web arayüzü : http://<sunucu-ip>:$webPort"
Write-Host "  Backend API : http://<sunucu-ip>:8000/api/health"
Write-Host "  Loglar      : docker compose logs -f"
Write-Host ""
Write-Warn2 "Sıradaki adımlar için DEPLOYMENT.md'ye bakın: ilk giriş, LDAP/SMTP/vCenter yapılandırması."
