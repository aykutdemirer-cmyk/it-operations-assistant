#!/usr/bin/env bash
# IT Operations Assistant — Agent systemd daemon'ını kaldırır.
#
# Kullanım (root/sudo ile):
#   sudo bash apps/agent/scripts/uninstall_linux_service.sh
#
# Servisi durdurur, systemd'den kaldırır ve unit dosyasını siler.
# `/opt/itops-agent` kurulum dizinine (ve içindeki `.env`/state
# dosyasına) BİLİNÇLİ olarak DOKUNMAZ — yeniden kurulumda aynı
# yapılandırma/agent kimliği kalsın diye; tamamen silmek isterseniz
# `--purge` bayrağıyla çalıştırın.

set -euo pipefail

SERVICE_NAME="itops-agent"
INSTALL_DIR="/opt/itops-agent"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
PURGE=false

for arg in "$@"; do
  if [[ "${arg}" == "--purge" ]]; then
    PURGE=true
  fi
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Bu script root/sudo yetkisi gerektirir. 'sudo bash $0' ile tekrar deneyin." >&2
  exit 1
fi

if systemctl list-unit-files "${SERVICE_NAME}.service" >/dev/null 2>&1 \
  && systemctl list-unit-files "${SERVICE_NAME}.service" | grep -q "${SERVICE_NAME}.service"; then
  echo "Servis durduruluyor ve devre dışı bırakılıyor..."
  systemctl stop "${SERVICE_NAME}" || true
  systemctl disable "${SERVICE_NAME}" || true
else
  echo "'${SERVICE_NAME}' servisi zaten kayıtlı değil — durdurma/disable adımı atlanıyor."
fi

if [[ -f "${UNIT_PATH}" ]]; then
  rm -f "${UNIT_PATH}"
  systemctl daemon-reload
  echo "Unit dosyası kaldırıldı: ${UNIT_PATH}"
fi

if [[ "${PURGE}" == true && -d "${INSTALL_DIR}" ]]; then
  echo "--purge verildi: ${INSTALL_DIR} tamamen siliniyor..."
  rm -rf "${INSTALL_DIR}"
fi

echo "Kaldırıldı: ${SERVICE_NAME}"
