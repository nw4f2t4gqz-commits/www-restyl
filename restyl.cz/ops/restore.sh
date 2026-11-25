#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

usage() {
  printf 'Usage: %s <backup-directory> --confirm\n' "$0" >&2
  printf 'This replaces the local Drupal database and overlays its files.\n' >&2
}

if [[ $# -ne 2 || "$2" != "--confirm" ]]; then
  usage
  exit 2
fi

ENV_FILE="${COMPOSE_ENV_FILE:-.env.example}"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-restyl-local}"
backup_dir="$1"
if [[ "$backup_dir" != /* ]]; then
  backup_dir="$PROJECT_ROOT/$backup_dir"
fi
backup_dir="$(cd "$backup_dir" && pwd)"

if [[ ! -f "$ENV_FILE" ]]; then
  printf 'Compose env file not found: %s\n' "$ENV_FILE" >&2
  exit 2
fi

for required in COMPLETE manifest.txt SHA256SUMS database.sql.gz files.tar.gz private.tar.gz; do
  if [[ ! -f "$backup_dir/$required" ]]; then
    printf 'Backup is incomplete; missing %s\n' "$required" >&2
    exit 2
  fi
done

(
  cd "$backup_dir"
  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 -c SHA256SUMS
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum -c SHA256SUMS
  else
    printf 'Need shasum or sha256sum to verify this backup.\n' >&2
    exit 2
  fi
)

for archive in database.sql.gz files.tar.gz private.tar.gz; do
  gzip -t "$backup_dir/$archive"
done
tar -tzf "$backup_dir/files.tar.gz" >/dev/null
tar -tzf "$backup_dir/private.tar.gz" >/dev/null

compose=(docker compose --project-name "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$PROJECT_ROOT/compose.yaml")
db_name="$("${compose[@]}" exec -T database sh -lc 'printf %s "$MARIADB_DATABASE"')"
backup_db_name="$(awk -F= '$1 == "database" { print substr($0, index($0, "=") + 1) }' "$backup_dir/manifest.txt")"
if [[ -z "$db_name" || "$db_name" != "$backup_db_name" || "$db_name" == *[!a-zA-Z0-9_]* ]]; then
  printf 'Backup database does not match the configured local database; refusing restore.\n' >&2
  exit 2
fi

printf 'Restore replaces database "%s", overlays Drupal files and restores the private site salt.\n' "$db_name"
printf 'A safety backup of the current stack will be created first.\n'
printf 'Proceeding only because --confirm was supplied.\n'

pre_restore_backup="$(
  COMPOSE_ENV_FILE="$ENV_FILE" \
    COMPOSE_PROJECT_NAME="$PROJECT_NAME" \
    "$PROJECT_ROOT/ops/backup.sh"
)"
printf 'Safety backup: %s\n' "$pre_restore_backup"

drupal_stopped=0
restart_drupal() {
  if [[ "$drupal_stopped" -eq 1 ]]; then
    "${compose[@]}" start drupal >/dev/null || true
    drupal_stopped=0
  fi
}
trap restart_drupal EXIT

"${compose[@]}" stop drupal
drupal_stopped=1

"${compose[@]}" exec -T database sh -lc '
  set -eu
  db="$MARIADB_DATABASE"
  case "$db" in
    ""|*[!a-zA-Z0-9_]*) printf "Unsupported database name\n" >&2; exit 2 ;;
  esac
  export MYSQL_PWD="$MARIADB_ROOT_PASSWORD"
  mariadb --user=root --execute="DROP DATABASE IF EXISTS \`$db\`; CREATE DATABASE \`$db\` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;"
'

gzip -dc "$backup_dir/database.sql.gz" | "${compose[@]}" exec -T database sh -lc '
  set -eu
  export MYSQL_PWD="$MARIADB_PASSWORD"
  mariadb --user="$MARIADB_USER" "$MARIADB_DATABASE"
'

drupal_container="$("${compose[@]}" ps -a -q drupal)"
drupal_image="$("${compose[@]}" images -q drupal)"
if [[ -z "$drupal_container" || -z "$drupal_image" ]]; then
  printf 'Cannot find the stopped Drupal container or its image for volume restore.\n' >&2
  exit 1
fi

gzip -dc "$backup_dir/files.tar.gz" | docker run --rm -i \
  --volumes-from "$drupal_container" --entrypoint tar "$drupal_image" \
  -xf - -C /var/www/html/web/sites/default/files

gzip -dc "$backup_dir/private.tar.gz" | docker run --rm -i \
  --volumes-from "$drupal_container" --entrypoint tar "$drupal_image" \
  -xf - -C /var/www/private

"${compose[@]}" start drupal
drupal_stopped=0
trap - EXIT

printf 'Restore complete. Files were overlaid; files absent from the archive were not deleted.\n'
