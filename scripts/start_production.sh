#!/usr/bin/env bash
set -Eeuo pipefail

: "${DJANGO_SETTINGS_MODULE:=config.settings.production}"
: "${GUNICORN_BIND:=127.0.0.1:8000}"
: "${GUNICORN_WORKERS:=2}"
: "${GUNICORN_THREADS:=1}"
: "${GUNICORN_TIMEOUT:=30}"
: "${GUNICORN_GRACEFUL_TIMEOUT:=30}"

case "$GUNICORN_WORKERS" in
  ''|*[!0-9]*) echo "GUNICORN_WORKERS must be a positive integer." >&2; exit 2 ;;
esac
case "$GUNICORN_THREADS" in
  ''|*[!0-9]*) echo "GUNICORN_THREADS must be a positive integer." >&2; exit 2 ;;
esac
case "$GUNICORN_TIMEOUT" in
  ''|*[!0-9]*) echo "GUNICORN_TIMEOUT must be a positive integer." >&2; exit 2 ;;
esac
case "$GUNICORN_GRACEFUL_TIMEOUT" in
  ''|*[!0-9]*) echo "GUNICORN_GRACEFUL_TIMEOUT must be a positive integer." >&2; exit 2 ;;
esac

if (( GUNICORN_WORKERS < 1 || GUNICORN_THREADS < 1 || GUNICORN_TIMEOUT < 1 || GUNICORN_GRACEFUL_TIMEOUT < 1 )); then
  echo "Gunicorn numeric settings must be positive." >&2
  exit 2
fi

export DJANGO_SETTINGS_MODULE

exec uv run --frozen --no-dev gunicorn config.wsgi:application \
  --bind "$GUNICORN_BIND" \
  --workers "$GUNICORN_WORKERS" \
  --threads "$GUNICORN_THREADS" \
  --timeout "$GUNICORN_TIMEOUT" \
  --graceful-timeout "$GUNICORN_GRACEFUL_TIMEOUT" \
  --access-logfile - \
  --error-logfile - \
  --capture-output
