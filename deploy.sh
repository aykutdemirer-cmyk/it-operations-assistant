#!/usr/bin/env bash
# deploy.sh — IT Operations Assistant'ı sıfır bir Ubuntu/Linux
# sunucusunda bağımsız olarak ayağa kaldırır.
#
# Kullanım:  bash deploy.sh
#
# Ne yapar / ne yapmaz:
#  - Docker Engine + Docker Compose plugin + Git eksikse kurar (apt).
#  - Kök `.env.example`'dan gerçek bir `.env` üretir — POSTGRES_PASSWORD/
#    JWT_SECRET_KEY/PAM_VAULT_SECRET_KEY rastgele, kriptografik olarak
#    güçlü üretilir; `.env` ZATEN VARSA dokunmaz (idempotent — ikinci
#    çalıştırma mevcut sırları asla üzerine yazmaz).
#  - "Migrasyon" adımı YOK (Alembic bu projede KULLANILMIYOR — ORM/
#    migration aracı hiç kullanılmadı). Şema TEK bir dosyadan (`infra/
#    postgres/init.sql`) gelir ve `api` servisinin kendisi başlarken
#    otomatik uygular (bkz. `apps/api/app/main.py::_ensure_schema_once`);
#    bu script yalnızca servisleri ayağa kaldırır, DDL'i KENDİSİ hiç
#    çalıştırmaz.
#  - Varsayılan Admin hesabını "admin/admin123" gibi TAHMİN EDİLEBİLİR
#    bir parolayla OLUŞTURMAZ — rastgele, güçlü bir parola üretip BİR
#    KEZ ekrana yazar (backend ilk açılışta `users` tablosu boşken bu
#    hesabı kendisi oluşturur, bkz. `_ensure_bootstrap_admin`).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

log()  { printf '\033[1;36m[deploy]\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m[deploy]\033[0m %s\n' "$1"; }
die()  { printf '\033[1;31m[deploy]\033[0m %s\n' "$1" >&2; exit 1; }

# ---- 1. Sistem bağımlılıkları --------------------------------------

if [[ "$(uname -s)" != "Linux" ]]; then
  die "Bu script yalnızca Linux (Ubuntu/Debian tabanlı, apt) içindir. Windows Server için deploy.ps1 kullanın."
fi

if ! command -v docker >/dev/null 2>&1; then
  log "Docker bulunamadı, kuruluyor (resmi Docker apt deposu)..."
  sudo apt-get update -y
  sudo apt-get install -y ca-certificates curl gnupg
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME:-jammy} stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt-get update -y
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  sudo systemctl enable --now docker
  log "Docker kuruldu. Bu kullanıcıyla parolasız 'docker' çalıştırabilmek için: sudo usermod -aG docker \$USER (sonra tekrar giriş yapın)."
else
  log "Docker zaten kurulu ($(docker --version))."
fi

if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
  warn "Eski bağımsız 'docker-compose' ikili dosyası kullanılıyor — Compose plugin (docker compose) önerilir."
else
  die "Docker Compose bulunamadı (docker-ce paketiyle gelmesi beklenirdi). Elle kurun: https://docs.docker.com/compose/install/"
fi
log "Compose komutu: $COMPOSE"

if ! command -v git >/dev/null 2>&1; then
  log "Git bulunamadı, kuruluyor..."
  sudo apt-get install -y git
fi

# ---- 2. .env üretimi (idempotent) ----------------------------------

random_secret() { openssl rand -base64 48 | tr -d '\n=+/' | cut -c1-48; }
random_fernet_key() {
  # Fernet anahtarı 32 ham baytın url-safe base64'ü OLMALI — düz rastgele
  # bir string DEĞİL (bkz. apps/api/.env.example). Python zaten Docker
  # kurulumunun bir parçası olarak host'ta genelde yoktur; openssl her
  # Ubuntu'da hazır bulunur, bu yüzden Python'a bağımlı KALINMADI.
  openssl rand -base64 32 | tr '+/' '-_' | tr -d '\n'
}

if [[ -f .env ]]; then
  log ".env zaten var — dokunulmadı (mevcut sırlar korunuyor)."
else
  log ".env üretiliyor (.env.example temel alınarak, rastgele sırlarla)..."
  cp .env.example .env

  POSTGRES_PASSWORD_VALUE="$(random_secret)"
  JWT_SECRET_VALUE="$(random_secret)"
  FERNET_VALUE="$(random_fernet_key)"
  ADMIN_PASSWORD_VALUE="$(random_secret | cut -c1-20)"

  sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${POSTGRES_PASSWORD_VALUE}|" .env
  sed -i "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=${JWT_SECRET_VALUE}|" .env
  sed -i "s|^PAM_VAULT_SECRET_KEY=.*|PAM_VAULT_SECRET_KEY=${FERNET_VALUE}|" .env
  sed -i "s|^BOOTSTRAP_ADMIN_PASSWORD=.*|BOOTSTRAP_ADMIN_PASSWORD=${ADMIN_PASSWORD_VALUE}|" .env

  log "Üretilen İLK ADMIN parolası (yalnızca bu makinenin ilk açılışında geçerli, BİR DAHA GÖSTERİLMEYECEK):"
  printf '\n    kullanıcı adı: admin\n    parola:        %s\n\n' "$ADMIN_PASSWORD_VALUE"
  warn "Bu parolayı şimdi güvenli bir yere kaydedin. İlk girişten sonra .env'deki BOOTSTRAP_ADMIN_PASSWORD satırını silmeniz önerilir (bkz. DEPLOYMENT.md)."
fi

# ---- 3. Kalıcı veri dizinleri ---------------------------------------

mkdir -p data/pam-recordings data/pam-drives
log "Kalıcı veri dizinleri hazır: ./data/pam-recordings, ./data/pam-drives"

# ---- 4. Build + başlat ----------------------------------------------

log "Servisler build edilip başlatılıyor (ilk çalıştırmada birkaç dakika sürebilir)..."
$COMPOSE up -d --build

log "Veritabanı hazır olması bekleniyor..."
for i in $(seq 1 30); do
  if $COMPOSE exec -T db pg_isready -U "$(grep '^POSTGRES_USER=' .env | cut -d= -f2)" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

log "Backend'in şemayı kurup sağlıklı olması bekleniyor..."
for i in $(seq 1 30); do
  if curl -fsS http://localhost:8000/api/health >/dev/null 2>&1; then
    log "Backend hazır: http://localhost:8000/api/health"
    break
  fi
  sleep 2
done

WEB_PORT="$(grep '^WEB_HTTP_PORT=' .env | cut -d= -f2)"
echo
log "Kurulum tamamlandı."
echo "  Web arayüzü : http://<sunucu-ip>:${WEB_PORT:-80}"
echo "  Backend API : http://<sunucu-ip>:8000/api/health"
echo "  Loglar      : $COMPOSE logs -f"
echo
warn "Sıradaki adımlar için DEPLOYMENT.md'ye bakın: ilk giriş, LDAP/SMTP/vCenter yapılandırması."
