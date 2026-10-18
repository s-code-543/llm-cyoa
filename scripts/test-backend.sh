#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
docker compose -f compose.dev.yml build web
docker run --rm --network none --entrypoint sh llm-cyoa-dev-web -c 'mkdir -p /app/db /app/staticfiles && python manage.py makemigrations --check --dry-run && python -m pytest "$@"' sh "$@"
