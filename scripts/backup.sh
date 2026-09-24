#!/usr/bin/env bash
#
# Nightly backup: the database and every uploaded document.
#
# setup_server.sh installs this at /usr/local/bin/titans-backup and runs it at
# 2am. Seven days are kept, one file per weekday, so the oldest is overwritten
# rather than filling the disk.
#
# This writes to the same server. That protects you from a bad migration or a
# deleted record — it does NOT protect you from losing the server. Copy these
# off the machine as well; DEPLOYMENT.md says how.

set -euo pipefail

APP_DIR=/srv/titans/app
OUT=/srv/titans/backups
DAY="$(date +%u)"          # 1..7, so a week rotates by itself

mkdir -p "$OUT"

# The database URL lives in .env, so the password is never on the command line.
DB_URL="$(grep -oP '(?<=^DATABASE_URL=).*' "$APP_DIR/.env")"

pg_dump "$DB_URL" | gzip > "$OUT/db-$DAY.sql.gz.part"
mv "$OUT/db-$DAY.sql.gz.part" "$OUT/db-$DAY.sql.gz"

if [[ -d "$APP_DIR/media" ]]; then
  tar czf "$OUT/media-$DAY.tgz.part" -C "$APP_DIR" media
  mv "$OUT/media-$DAY.tgz.part" "$OUT/media-$DAY.tgz"
fi

echo "$(date '+%Y-%m-%d %H:%M')  backed up to $OUT (slot $DAY)"

# If rclone is set up, push a copy off the server too. Nothing happens if it
# is not — see DEPLOYMENT.md for the five minutes it takes to add.
if command -v rclone >/dev/null && rclone listremotes 2>/dev/null | grep -q '^titans-offsite:'; then
  rclone copy "$OUT" titans-offsite:titans-backups --include "*-$DAY.*" --quiet
  echo "  copied off the server with rclone"
fi
