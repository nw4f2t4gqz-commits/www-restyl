#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

ENV_FILE="${COMPOSE_ENV_FILE:-.env.example}"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-restyl-local}"
BACKUP_PARENT="${1:-$PROJECT_ROOT/backups}"

if [[ ! -f "$ENV_FILE" ]]; then
  printf 'Compose env file not found: %s\n' "$ENV_FILE" >&2
  exit 2
fi

if [[ "$BACKUP_PARENT" != /* ]]; then
  BACKUP_PARENT="$PROJECT_ROOT/$BACKUP_PARENT"
fi
mkdir -p "$BACKUP_PARENT"

compose=(docker compose --project-name "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$PROJECT_ROOT/compose.yaml")
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="$BACKUP_PARENT/restyl-$timestamp"
mkdir "$backup_dir"
chmod 700 "$backup_dir"

db_name="$("${compose[@]}" exec -T database sh -lc 'printf %s "$MARIADB_DATABASE"')"
if [[ -z "$db_name" || "$db_name" == *[!a-zA-Z0-9_]* ]]; then
  printf 'Unsupported database name for backup: %s\n' "$db_name" >&2
  exit 2
fi

cleanup() {
  rm -f "$backup_dir/database.sql.gz.partial" \
    "$backup_dir/files.tar.gz.partial" \
    "$backup_dir/private.tar.gz.partial"
}
trap cleanup EXIT

"${compose[@]}" exec -T database sh -lc '
  set -eu
  export MYSQL_PWD="$MARIADB_PASSWORD"
  mariadb-dump --user="$MARIADB_USER" --single-transaction --quick --skip-lock-tables "$MARIADB_DATABASE"
' | gzip -c > "$backup_dir/database.sql.gz.partial"

"${compose[@]}" exec -T drupal tar -czf - \
  -C /var/www/html/web/sites/default/files . \
  > "$backup_dir/files.tar.gz.partial"

"${compose[@]}" exec -T drupal tar -czf - \
  -C /var/www/private . \
  > "$backup_dir/private.tar.gz.partial"

for archive in "$backup_dir"/*.partial; do
  [[ -s "$archive" ]] || {
    printf 'Backup archive is empty: %s\n' "$archive" >&2
    exit 1
  }
  gzip -t "$archive"
done
tar -tzf "$backup_dir/files.tar.gz.partial" >/dev/null
tar -tzf "$backup_dir/private.tar.gz.partial" >/dev/null

mv "$backup_dir/database.sql.gz.partial" "$backup_dir/database.sql.gz"
mv "$backup_dir/files.tar.gz.partial" "$backup_dir/files.tar.gz"
mv "$backup_dir/private.tar.gz.partial" "$backup_dir/private.tar.gz"

cat > "$backup_dir/manifest.txt" <<EOF
created_utc=$timestamp
compose_project=$PROJECT_NAME
database=$db_name
includes=database,drupal-public-files,drupal-private-hash-salt
EOF

(
  cd "$backup_dir"
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 database.sql.gz files.tar.gz private.tar.gz > SHA256SUMS
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum database.sql.gz files.tar.gz private.tar.gz > SHA256SUMS
  else
    printf 'Need shasum or sha256sum to write backup checksums.\n' >&2
    exit 2
  fi
)

touch "$backup_dir/COMPLETE"
chmod 600 "$backup_dir"/*
printf '%s\n' "$backup_dir"
