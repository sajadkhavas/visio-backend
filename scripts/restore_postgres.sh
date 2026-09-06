#!/usr/bin/env bash
set -Eeuo pipefail

: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
: "${POSTGRES_HOST:?POSTGRES_HOST is required}"
: "${POSTGRES_PORT:=5432}"
: "${VISIO_BACKUP_PATH:?VISIO_BACKUP_PATH is required}"
: "${VISIO_RESTORE_DATABASE:?VISIO_RESTORE_DATABASE is required}"

if [[ "$VISIO_RESTORE_DATABASE" == "$POSTGRES_DB" ]]; then
    echo "Refusing to restore over the source database." >&2
    exit 2
fi
if [[ ! -f "$VISIO_BACKUP_PATH" || ! -f "${VISIO_BACKUP_PATH}.sha256" ]]; then
    echo "Backup archive or checksum is missing." >&2
    exit 2
fi

(
    cd "$(dirname "$VISIO_BACKUP_PATH")"
    sha256sum --check "$(basename "${VISIO_BACKUP_PATH}.sha256")"
)

export PGPASSWORD="$POSTGRES_PASSWORD"
pg_restore \
    --host="$POSTGRES_HOST" \
    --port="$POSTGRES_PORT" \
    --username="$POSTGRES_USER" \
    --dbname="$VISIO_RESTORE_DATABASE" \
    --exit-on-error \
    --no-owner \
    --no-privileges \
    "$VISIO_BACKUP_PATH"

echo "Backup restored into disposable target: $VISIO_RESTORE_DATABASE"
