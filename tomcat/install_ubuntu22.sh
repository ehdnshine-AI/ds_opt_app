#!/usr/bin/env bash

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "[error] run as root: sudo $0"
  exit 1
fi

APP_USER="${APP_USER:-dsopt}"
APP_GROUP="${APP_GROUP:-dsopt}"
APP_DIR="${APP_DIR:-/opt/ds_opt_app/current}"
VENV_DIR="${VENV_DIR:-/opt/ds_opt_app/venv}"
LOG_DIR="${LOG_DIR:-/var/log/ds_opt_app}"
RUN_DIR="${RUN_DIR:-/var/run/ds_opt_app}"
ENV_DIR="${ENV_DIR:-/etc/ds_opt_app}"
INSTALL_TOMCAT_ADMIN="${INSTALL_TOMCAT_ADMIN:-1}"

COMMON_PACKAGES=(
  nginx
  openjdk-17-jdk
  tomcat10
  python3
  python3-venv
  python3-pip
  build-essential
  pkg-config
  curl
  git
)

OPTIONAL_PACKAGES=(
  python3-dev
  libpq-dev
)

echo "[info] apt update"
apt-get update

if [[ "${INSTALL_TOMCAT_ADMIN}" == "1" ]]; then
  COMMON_PACKAGES+=(tomcat10-admin)
fi

echo "[info] installing packages"
apt-get install -y "${COMMON_PACKAGES[@]}" "${OPTIONAL_PACKAGES[@]}"

if ! getent group "${APP_GROUP}" >/dev/null; then
  echo "[info] creating group ${APP_GROUP}"
  groupadd --system "${APP_GROUP}"
fi

if ! id -u "${APP_USER}" >/dev/null 2>&1; then
  echo "[info] creating user ${APP_USER}"
  useradd --system --gid "${APP_GROUP}" --home-dir /opt/ds_opt_app --shell /usr/sbin/nologin "${APP_USER}"
fi

echo "[info] creating directories"
install -d -o "${APP_USER}" -g "${APP_GROUP}" "${APP_DIR}"
install -d -o "${APP_USER}" -g "${APP_GROUP}" "${VENV_DIR}"
install -d -o "${APP_USER}" -g "${APP_GROUP}" "${LOG_DIR}"
install -d -o "${APP_USER}" -g "${APP_GROUP}" "${RUN_DIR}"
install -d -o root -g root "${ENV_DIR}"

echo "[info] package summary"
java -version || true
python3 --version || true
nginx -v || true
systemctl status tomcat10 --no-pager || true

cat <<EOF

[ok] base packages installed

Next steps:
  1. Deploy project files to: ${APP_DIR}
  2. Create venv:
       sudo -u ${APP_USER} python3 -m venv ${VENV_DIR}
       sudo -u ${APP_USER} ${VENV_DIR}/bin/pip install --upgrade pip
       sudo -u ${APP_USER} ${VENV_DIR}/bin/pip install -r ${APP_DIR}/requirements.txt
  3. Create env files under: ${ENV_DIR}
  4. Run:
       sudo APP_DIR=${APP_DIR} APP_USER=${APP_USER} APP_GROUP=${APP_GROUP} VENV_DIR=${VENV_DIR} bash tomcat/setup_systemd.sh
       sudo APP_DIR=${APP_DIR} SERVER_NAME=example.com bash tomcat/setup_nginx_tomcat.sh

EOF
