#!/usr/bin/env bash
# IT Operations Assistant — Agent'ı systemd daemon'ı olarak kurar.
#
# Kullanım (root/sudo ile, herhangi bir dizinden):
#   sudo bash apps/agent/scripts/install_linux_service.sh
#
# Ne yapar:
#   1. root/sudo yetkisi kontrolü.
#   2. Bu repodaki apps/agent'ı /opt/itops-agent'a kopyalar, bir Python
#      venv kurar (yalnızca runtime bağımlılığı: psutil — bkz.
#      requirements.txt), sistemde zaten yoksa `itops-agent` adında
#      home dizini olmayan bir sistem kullanıcısı/grubu oluşturur.
#   3. /etc/systemd/system/itops-agent.service dosyasını GERÇEK
#      path'lerle üretir (bkz. deploy/systemd/itops-agent.service —
#      o dosya yalnızca REFERANS şablonudur, bu script'in çıktısı onun
#      yerini alır, elle senkron tutulması gerekmez):
#        ExecStart  = <venv>/bin/python -m agent start (tam yol)
#        Restart    = always
#        RestartSec = 5
#   4. systemctl daemon-reload && systemctl enable itops-agent &&
#      systemctl start itops-agent
#
# Önkoşul: kurulumdan ÖNCE bu script'in yanındaki (apps/agent/) dizinde
# bir `.env` dosyası — en azından BACKEND_URL ve (ilk kayıt için)
# ENROLLMENT_CODE (Ayarlar > Agent Yapılandırması'ndan üretilir). Bu
# `.env`, /opt/itops-agent/.env'e KOPYALANIR (kaynak dosyaya
# dokunulmaz).
#
# Kaldırmak için: uninstall_linux_service.sh.

set -euo pipefail

SERVICE_NAME="itops-agent"
INSTALL_DIR="/opt/itops-agent"
SERVICE_USER="itops-agent"
UNIT_PATH="/etc/systemd/system/${SERVICE_NAME}.service"

# --- 1. root/sudo yetkisi kontrolü ---
if [[ "$(id -u)" -ne 0 ]]; then
  echo "Bu script root/sudo yetkisi gerektirir. 'sudo bash $0' ile tekrar deneyin." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_SOURCE="${AGENT_ROOT}/.env"

if [[ ! -f "${ENV_SOURCE}" ]]; then
  echo "UYARI: ${ENV_SOURCE} bulunamadi. Servis BACKEND_URL/ENROLLMENT_CODE olmadan baslayamaz." >&2
  echo "Devam etmeden once 'apps/agent/.env' dosyasini olusturun (ornek: apps/agent/.env.example)." >&2
fi

# --- 2. Kurulum dizini + servis hesabi + venv ---
if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  echo "Sistem kullanicisi olusturuluyor: ${SERVICE_USER}"
  useradd --system --no-create-home --shell /usr/sbin/nologin "${SERVICE_USER}"
fi

echo "Agent kaynagi kopyalaniyor: ${AGENT_ROOT} -> ${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"
# `.venv`/`dist`/`build`/`__pycache__` KOPYALANMAZ — hedefte temiz bir
# venv kurulur, build/dist yalnızca Windows tarafina özel.
rsync -a --delete \
  --exclude ".venv" --exclude "dist" --exclude "build" \
  --exclude "__pycache__" --exclude "*.pyc" --exclude ".pytest_cache" \
  "${AGENT_ROOT}/" "${INSTALL_DIR}/"

if [[ -f "${ENV_SOURCE}" ]]; then
  cp "${ENV_SOURCE}" "${INSTALL_DIR}/.env"
fi

PYTHON_BIN="$(command -v python3 || command -v python)"
if [[ -z "${PYTHON_BIN}" ]]; then
  echo "python3 bulunamadi — once Python 3 kurun." >&2
  exit 1
fi

echo "Python venv kuruluyor: ${INSTALL_DIR}/.venv"
"${PYTHON_BIN}" -m venv "${INSTALL_DIR}/.venv"
"${INSTALL_DIR}/.venv/bin/pip" install --upgrade pip >/dev/null
"${INSTALL_DIR}/.venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"

# --- 3. systemd unit dosyasini gercek path'lerle uret ---
echo "systemd unit dosyasi yaziliyor: ${UNIT_PATH}"
cat > "${UNIT_PATH}" <<EOF
[Unit]
Description=IT Operations Assistant Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_USER}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${INSTALL_DIR}/.venv/bin/python -m agent start
Restart=always
RestartSec=5

# Sertlestirme (kurulumun izin verdigi olcude) — agent'in kendi state/
# log dosyalari disinda dosya sistemine yazma ihtiyaci yok.
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=${INSTALL_DIR}

[Install]
WantedBy=multi-user.target
EOF

# --- 4. Servisi tanit ve baslat ---
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

echo ""
echo "Kurulum tamamlandi. Durum: systemctl status ${SERVICE_NAME}"
echo "Loglar: journalctl -u ${SERVICE_NAME} -f"
