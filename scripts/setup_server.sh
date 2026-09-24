#!/usr/bin/env bash
#
# Set up Titans Windows CRM on a fresh Ubuntu server (Oracle Cloud, or any VPS).
#
#   sudo bash setup_server.sh crm.yourdomain.com you@yourdomain.com
#
# Installs PostgreSQL, the app, gunicorn under systemd, nginx, and a free HTTPS
# certificate. Safe to run again — it skips anything already done, and never
# overwrites an existing .env or database.
#
# It does NOT open the ports in the Oracle console. That is a click in the web
# console and cannot be scripted; DEPLOYMENT.md says where.

set -euo pipefail

DOMAIN="${1:-}"
EMAIL="${2:-}"
REPO="${TITANS_REPO:-https://github.com/darshansathish2006/TITANS.git}"
APP_DIR=/srv/titans/app
APP_USER=titans

if [[ -z "$DOMAIN" ]]; then
  echo "Usage: sudo bash setup_server.sh <domain> [email-for-certificate]" >&2
  echo "   eg: sudo bash setup_server.sh crm.titanswindows.in admin@titanswindows.in" >&2
  exit 1
fi
if [[ $EUID -ne 0 ]]; then
  echo "Run this with sudo." >&2
  exit 1
fi

say() { printf "\n\033[1;33m==> %s\033[0m\n" "$1"; }

# ---------------------------------------------------------------- packages
say "Installing what the server needs"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip python3-dev build-essential \
  libpq-dev postgresql postgresql-contrib nginx git curl \
  certbot python3-certbot-nginx iptables-persistent

# ------------------------------------------------------------------- ports
# Oracle's Ubuntu images drop everything except SSH in iptables, on top of the
# security list in the console. Both have to allow 80 and 443.
say "Opening ports 80 and 443 on the server itself"
for port in 80 443; do
  if ! iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null; then
    iptables -I INPUT 6 -m state --state NEW -p tcp --dport "$port" -j ACCEPT
    echo "  opened $port"
  else
    echo "  $port already open"
  fi
done
netfilter-persistent save >/dev/null

# ---------------------------------------------------------------- database
say "Setting up PostgreSQL"
DB_NAME=titans
DB_USER=titans
if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
  echo "  database user already exists, leaving its password alone"
  DB_PASS="$(grep -oP '(?<=DATABASE_URL=postgres://titans:)[^@]+' "$APP_DIR/.env" 2>/dev/null || true)"
  if [[ -z "$DB_PASS" ]]; then
    echo "  !! could not read the existing password from $APP_DIR/.env" >&2
    echo "     Fix .env by hand, or drop the '$DB_USER' role and run this again." >&2
    exit 1
  fi
else
  DB_PASS="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
  sudo -u postgres psql -q -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';"
  echo "  created the database user"
fi
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1; then
  sudo -u postgres psql -q -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
  echo "  created the database"
fi

# --------------------------------------------------------------- the code
say "Fetching the application"
id -u "$APP_USER" >/dev/null 2>&1 || adduser --system --group --home /srv/titans "$APP_USER"
mkdir -p /srv/titans
chown "$APP_USER:$APP_USER" /srv/titans
if [[ -d "$APP_DIR/.git" ]]; then
  sudo -u "$APP_USER" git -C "$APP_DIR" pull --ff-only
else
  sudo -u "$APP_USER" git clone --quiet "$REPO" "$APP_DIR"
fi
[[ -d "$APP_DIR/venv" ]] || sudo -u "$APP_USER" python3 -m venv "$APP_DIR/venv"
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

# -------------------------------------------------------------- settings
if [[ -f "$APP_DIR/.env" ]]; then
  say "Keeping the .env that is already there"
else
  say "Writing $APP_DIR/.env"
  SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')"
  cat > "$APP_DIR/.env" <<EOF
DJANGO_SECRET_KEY=$SECRET
DEBUG=False
ALLOWED_HOSTS=$DOMAIN
CSRF_TRUSTED_ORIGINS=https://$DOMAIN
DATABASE_URL=postgres://$DB_USER:$DB_PASS@localhost:5432/$DB_NAME
TIME_ZONE=Asia/Kolkata
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
# Turn HSTS on only once HTTPS has been working for a day or two.
SECURE_HSTS_SECONDS=0
EOF
  chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
fi

say "Preparing the database and the staff accounts"
sudo -u "$APP_USER" "$APP_DIR/venv/bin/python" "$APP_DIR/manage.py" migrate --noinput
sudo -u "$APP_USER" "$APP_DIR/venv/bin/python" "$APP_DIR/manage.py" collectstatic --noinput >/dev/null
sudo -u "$APP_USER" "$APP_DIR/venv/bin/python" "$APP_DIR/manage.py" seed_employees
mkdir -p "$APP_DIR/media" && chown -R "$APP_USER:$APP_USER" "$APP_DIR/media"

# ------------------------------------------------------------ run it
say "Running it as a service"
cat > /etc/systemd/system/titans.service <<EOF
[Unit]
Description=Titans Windows CRM
After=network.target postgresql.service

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/gunicorn titans_crm.wsgi:application \\
  --bind 127.0.0.1:8000 --workers 3 --timeout 120
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now titans
systemctl restart titans

# --------------------------------------------------------------- nginx
say "Putting nginx in front"
cat > /etc/nginx/sites-available/titans <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;

    # Uploaded documents and scanned measurements can be large.
    client_max_body_size 32M;

    location /static/ {
        alias $APP_DIR/staticfiles/;
        access_log off;
        expires 30d;
    }

    # /media/ is deliberately NOT served by nginx — the app checks who is
    # asking before handing over a customer's paperwork.

    # Android checks this file to decide whether the .apk really belongs to
    # this site; without it the app shows a browser address bar. Bubblewrap
    # prints the file — drop it at the path below. Harmless until then.
    # An exact match, so it cannot shadow certbot's renewal challenge.
    location = /.well-known/assetlinks.json {
        alias /srv/titans/assetlinks.json;
        default_type application/json;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }
}
EOF
ln -sf /etc/nginx/sites-available/titans /etc/nginx/sites-enabled/titans
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

# ----------------------------------------------------------- certificate
say "Getting a free HTTPS certificate"
if [[ -n "$EMAIL" ]]; then
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" --redirect || {
    echo
    echo "  Certificate failed. Almost always one of:"
    echo "   - $DOMAIN does not point at this server's public IP yet (DNS)"
    echo "   - ports 80/443 are not open in the Oracle console security list"
    echo "  Fix that, then run:  sudo certbot --nginx -d $DOMAIN"
  }
else
  echo "  No email given, so skipping. Run this when DNS is ready:"
  echo "    sudo certbot --nginx -d $DOMAIN"
fi

# -------------------------------------------------------------- backups
say "Setting up nightly backups"
install -m 755 "$APP_DIR/scripts/backup.sh" /usr/local/bin/titans-backup
mkdir -p /srv/titans/backups && chown "$APP_USER:$APP_USER" /srv/titans/backups
( crontab -l 2>/dev/null | grep -v titans-backup; echo "0 2 * * * /usr/local/bin/titans-backup" ) | crontab -

say "Done"
cat <<EOF

  Site         https://$DOMAIN
  Sign in as   admin  /  ChangeMe@123   (you will be asked to change it)
  Backups      nightly at 2am into /srv/titans/backups, seven days kept

  Check it:    systemctl status titans
  Logs:        journalctl -u titans -f
  Update:      sudo bash $APP_DIR/scripts/setup_server.sh $DOMAIN

  Still to do by hand: copy the backups somewhere off this server.
  DEPLOYMENT.md explains how.

EOF
