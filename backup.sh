#!/usr/bin/env bash
# backup.sh — PostgreSQL veritabanının (ve PAM oturum kaydı/sürücü
# dosyalarının) tam bir yedeğini alır. Docker Compose ile GERÇEKTEN
# çalışan `db` servisinin İÇİNDEN `pg_dump` çalıştırır — ayrı bir
# PostgreSQL istemcisi bu makinede kurulu olmak ZORUNDA DEĞİL.
#
# Kullanım:  bash backup.sh [hedef-dizin]   (varsayılan: ./backups)

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

log()  { printf '\033[1;36m[backup]\033[0m %s\n' "$1"; }
die()  { printf '\033[1;31m[backup]\033[0m %s\n' "$1" >&2; exit 1; }

[[ -f .env ]] || die ".env bulunamadı — önce deploy.sh/deploy.ps1 ile kurulum yapın."
# shellcheck disable=SC1091
set -a; source .env; set +a

if docker compose version >/dev/null 2>&1; then COMPOSE="docker compose"; else COMPOSE="docker-compose"; fi

BACKUP_DIR="${1:-./backups}"
mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
DB_DUMP="$BACKUP_DIR/itops-db-$STAMP.sql.gz"
DATA_ARCHIVE="$BACKUP_DIR/itops-data-$STAMP.tar.gz"

log "PostgreSQL yedeği alınıyor ($DB_DUMP)..."
$COMPOSE exec -T db pg_dump -U "${POSTGRES_USER:-itops}" "${POSTGRES_DB:-itops}" | gzip > "$DB_DUMP"

if [[ -d data ]]; then
  log "PAM oturum kaydı/sürücü dosyaları yedekleniyor ($DATA_ARCHIVE)..."
  tar -czf "$DATA_ARCHIVE" data/
else
  log "./data dizini yok, atlandı (henüz oturum kaydı yok)."
fi

log "Tamamlandı:"
echo "  $DB_DUMP"
[[ -f "$DATA_ARCHIVE" ]] && echo "  $DATA_ARCHIVE"
echo
log "NOT: .env dosyanız (sırlar: JWT_SECRET_KEY/PAM_VAULT_SECRET_KEY/POSTGRES_PASSWORD) bu yedeğe DAHİL EDİLMEDİ — kasıtlı (yedek dosyası daha az hassas bir konuma kopyalanabilir). .env'i AYRICA, güvenli bir şekilde (ör. bir parola yöneticisi/kasa) saklayın; PAM_VAULT_SECRET_KEY kaybolursa kasadaki (vault_credentials) şifreli parolalar KALICI OLARAK okunamaz hale gelir."
