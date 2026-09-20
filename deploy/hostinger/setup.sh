#!/usr/bin/env bash
# Hostinger VPS (Ubuntu): install and start ICCPP on iccppglobal.com
# Run from the project folder as root, after you have uploaded ENG to /var/www/iccpp:
#   sudo bash deploy/hostinger/setup.sh
set -euo pipefail

DOMAIN="iccppglobal.com"
APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run this as root: sudo bash deploy/hostinger/setup.sh"
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

if [[ ! -f "$APP_DIR/.env" ]]; then
  KEY="$("$APP_DIR/.venv/bin/python" -c "import secrets; print(secrets.token_hex(32))")"
  cat > "$APP_DIR/.env" <<EOF
ADMIN_USER=admin
ADMIN_PASSWORD=iccpp-admin
SECRET_KEY=$KEY
PRODUCTION=1
EOF
  echo "Created $APP_DIR/.env — change ADMIN_PASSWORD before going live."
fi

chown -R www-data:www-data "$APP_DIR"
chmod 640 "$APP_DIR/.env"

install -m 644 "$APP_DIR/deploy/hostinger/iccpp.service" /etc/systemd/system/iccpp.service
sed -i "s|/var/www/iccpp|$APP_DIR|g" /etc/systemd/system/iccpp.service

install -m 644 "$APP_DIR/deploy/hostinger/nginx-iccpp.conf" /etc/nginx/sites-available/iccpp
sed -i "s|/var/www/iccpp|$APP_DIR|g" /etc/nginx/sites-available/iccpp
ln -sfn /etc/nginx/sites-available/iccpp /etc/nginx/sites-enabled/iccpp
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl daemon-reload
systemctl enable --now iccpp
systemctl restart nginx

if command -v ufw >/dev/null 2>&1; then
  ufw allow 'Nginx Full' || true
fi

echo
echo "Site service is running."
echo "Point $DOMAIN and www.$DOMAIN A records to this VPS IP, then run:"
echo "  sudo certbot --nginx -d $DOMAIN -d www.$DOMAIN"
echo "Admin: https://www.$DOMAIN/admin"
