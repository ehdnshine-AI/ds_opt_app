#!/usr/bin/env bash

set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "[error] run as root: sudo $0"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SERVER_NAME="${SERVER_NAME:-_}"
SITE_NAME="${SITE_NAME:-ds_opt_app}"
NGINX_SITES_AVAILABLE="/etc/nginx/sites-available"
NGINX_SITES_ENABLED="/etc/nginx/sites-enabled"
APP_DIR="${APP_DIR:-/opt/ds_opt_app/current}"
TOMCAT_ROOT_DIR="${TOMCAT_ROOT_DIR:-/var/lib/tomcat10/webapps/ROOT}"
NGINX_CONF_PATH="${NGINX_SITES_AVAILABLE}/${SITE_NAME}.conf"

echo "[info] rendering nginx config"
sed \
  -e "s|__SERVER_NAME__|${SERVER_NAME}|g" \
  "${SCRIPT_DIR}/nginx/ds_opt_app.conf" > "${NGINX_CONF_PATH}"

ln -sf "${NGINX_CONF_PATH}" "${NGINX_SITES_ENABLED}/${SITE_NAME}.conf"
rm -f "${NGINX_SITES_ENABLED}/default"

echo "[info] installing sample Tomcat ROOT page"
install -d -o root -g root "${TOMCAT_ROOT_DIR}"
install -m 0644 "${SCRIPT_DIR}/tomcat-root/index.jsp" "${TOMCAT_ROOT_DIR}/index.jsp"

echo "[info] validating nginx config"
nginx -t

systemctl enable nginx tomcat10
systemctl restart tomcat10
systemctl reload nginx

cat <<EOF

[ok] nginx and tomcat files installed

Applied files:
  nginx: ${NGINX_CONF_PATH}
  tomcat root: ${TOMCAT_ROOT_DIR}/index.jsp

Verify:
  curl -I http://127.0.0.1/
  curl http://127.0.0.1/healthz
  curl http://127.0.0.1/docs

EOF
