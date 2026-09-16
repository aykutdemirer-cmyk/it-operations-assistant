#!/usr/bin/env bash
# restore.sh — backup.sh ile alınmış bir yedeği geri yükler.
#
# UYARI: bu işlem YIKICIDIR — hedef veritabanındaki TÜM mevcut veri
# silinip yedekteki veriyle DEĞİŞTİRİLİR. Onay istemeden çalışmaz.
#
# Kullanım:  bash restore.sh <itops-db-YYYYmmdd-HHMMSS.sql.gz> [itops-data-....tar.gz]

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

log()  { printf '\033[1;36m[restore]\033[0m %s\n' "$1"; }
warn() { printf '\033[1;33m[restore]\033[0m %s\n' "$1"; }
die()  { printf '\033[1;31m[restore]\033[0m %s\n' "$1" >&2; exit 1; }

DB_DUMP="${1:-}"
DATA_ARCHIVE="${2:-}"

[[ -n "$DB_DUMP" ]] || die "Kullanım: bash restore.sh <db-yedegi.sql.gz> [data-yedegi.tar.gz]"
[[ -f "$DB_DUMP" ]] || die "Dosya bulunamadı: $DB_DUMP"
[[ -f .env ]] || die ".env bulunamadı — önce deploy.sh ile kurulum yapın."
# shellcheck disable=SC1091
set -a; source .env; set +a

if docker compose version >/dev/null 2>&1; then COMPOSE="docker compose"; else COMPOSE="docker-compose"; fi

warn "Bu işlem '${POSTGRES_DB:-itops}' veritabanındaki TÜM mevcut veriyi SİLECEK ve '$DB_DUMP' içeriğiyle değiştirecek."
read -r -p "Devam etmek istediğinize emin misiniz? Yazın: EVET  " CONFIRM
[[ "$CONFIRM" == "EVET" ]] || die "İptal edildi."

log "Uygulama servisleri durduruluyor (restore sırasında yazma olmasın diye: api, web)..."
$COMPOSE stop api web

log "Veritabanı sıfırlanıp yedek geri yükleniyor..."
$COMPOSE exec -T db psql -U "${POSTGRES_USER:-itops}" -d postgres -c \
  "DROP DATABASE IF EXISTS \"${POSTGRES_DB:-itops}\"; CREATE DATABASE \"${POSTGRES_DB:-itops}\" OWNER \"${POSTGRES_USER:-itops}\";"
gunzip -c "$DB_DUMP" | $COMPOSE exec -T db psql -U "${POSTGRES_USER:-itops}" -d "${POSTGRES_DB:-itops}"
log "Veritabanı geri yüklendi."

if [[ -n "$DATA_ARCHIVE" ]]; then
  [[ -f "$DATA_ARCHIVE" ]] || die "Dosya bulunamadı: $DATA_ARCHIVE"
  log "PAM oturum kaydı/sürücü dosyaları geri yükleniyor..."
  rm -rf data
  tar -xzf "$DATA_ARCHIVE"
  log "./data geri yüklendi."
else
  warn "Bir data-yedeği belirtilmedi — PAM oturum kayıtları/dosya transferleri geri YÜKLENMEDİ (yalnızca veritabanı)."
fi

log "Servisler tekrar başlatılıyor..."
$COMPOSE up -d

log "Geri yükleme tamamlandı."
