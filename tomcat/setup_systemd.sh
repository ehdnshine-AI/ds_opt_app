#!/usr/bin/env bash

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "[error] run as root: sudo $0"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

APP_USER="${APP_USER:-dsopt}"
APP_GROUP="${APP_GROUP:-dsopt}"
APP_DIR="${APP_DIR:-/opt/ds_opt_app/current}"
VENV_DIR="${VENV_DIR:-/opt/ds_opt_app/venv}"
LOG_DIR="${LOG_DIR:-/var/log/ds_opt_app}"
ENV_DIR="${ENV_DIR:-/etc/ds_opt_app}"
SYSTEMD_DIR="/etc/systemd/system"

render_template() {
  local src="$1"
  local dst="$2"

  sed \
    -e "s|__APP_USER__|${APP_USER}|g" \
    -e "s|__APP_GROUP__|${APP_GROUP}|g" \
    -e "s|__APP_DIR__|${APP_DIR}|g" \
    -e "s|__VENV_DIR__|${VENV_DIR}|g" \
    -e "s|__LOG_DIR__|${LOG_DIR}|g" \
    -e "s|__ENV_DIR__|${ENV_DIR}|g" \
    "${src}" > "${dst}"
}

echo "[info] installing systemd services"
render_template "${SCRIPT_DIR}/systemd/ds-opt-api.service" "${SYSTEMD_DIR}/ds-opt-api.service"

chmod 0644 "${SYSTEMD_DIR}/ds-opt-api.service"

systemctl daemon-reload

cat <<EOF

[ok] systemd unit files installed

Recommended commands:
  sudo systemctl enable --now ds-opt-api
  sudo systemctl status ds-opt-api --no-pager

EOF
