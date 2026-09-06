#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${POSTGRES_HOST:?POSTGRES_HOST is required}"
: "${POSTGRES_PORT:=5432}"
: "${VISIO_BACKUP_PATH:?VISIO_BACKUP_PATH is required}"

if [[ -e "$VISIO_BACKUP_PATH" || -e "${VISIO_BACKUP_PATH}.sha256" ]]; then
    echo "Refusing to overwrite an existing backup or checksum." >&2
    exit 2
fi

backup_dir="$(dirname "$VISIO_BACKUP_PATH")"
mkdir -p "$backup_dir"

tmp_path="${VISIO_BACKUP_PATH}.tmp.$$"
cleanup() {
    rm -f "$tmp_path"
}
trap cleanup EXIT

export PGPASSWORD="$POSTGRES_PASSWORD"
pg_dump \
    --host="$POSTGRES_HOST" \
    --port="$POSTGRES_PORT" \
    --username="$POSTGRES_USER" \
    --dbname="$POSTGRES_DB" \
    --format=custom \
    --no-owner \
    --no-privileges \
    --file="$tmp_path"

mv "$tmp_path" "$VISIO_BACKUP_PATH"
sha256sum "$VISIO_BACKUP_PATH" > "${VISIO_BACKUP_PATH}.sha256"
chmod 600 "$VISIO_BACKUP_PATH" "${VISIO_BACKUP_PATH}.sha256"

echo "Backup created: $VISIO_BACKUP_PATH"
