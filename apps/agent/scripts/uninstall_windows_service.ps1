# IT Operations Assistant — Agent Windows Servisi'ni kaldırır.
#
# Kullanım (Yönetici PowerShell'den):
#   powershell -File apps/agent/scripts/uninstall_windows_service.ps1
#
# Servisi durdurur (`sc stop`) ve siler (`sc delete`) — build edilen
# EXE'ye (`dist/itops-agent.exe`) veya `.env`'e DOKUNMAZ, yalnızca
# servis kaydını kaldırır.

$ErrorActionPreference = "Stop"
$ServiceName = "ITOpsAgent"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Bu script Yönetici (Administrator) yetkisi gerektirir. PowerShell'i 'Yönetici olarak çalıştır' ile yeniden açıp tekrar deneyin."
    exit 1
}

$existing = sc.exe query $ServiceName 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "'$ServiceName' servisi zaten kayıtlı değil - yapılacak bir şey yok."
    exit 0
}

Write-Host "Servis durduruluyor..."
sc.exe stop $ServiceName | Out-Null
Start-Sleep -Seconds 2

Write-Host "Servis kaldırılıyor..."
sc.exe delete $ServiceName
if ($LASTEXITCODE -ne 0) {
    Write-Error "sc.exe delete başarısız oldu (exit code $LASTEXITCODE)"
    exit 1
}

Write-Host "Kaldırıldı: $ServiceName"
