#!/bin/bash
# Entrypoint script for CYOA Game Server container

set -e

echo "🎲 Starting CYOA Game Server..."

# Run migrations (idempotent - safe to run on every startup)
echo "📦 Running migrations..."
python manage.py migrate --noinput

# Collect static files (idempotent - safe to run on every startup)
echo "📂 Collecting static files..."
python manage.py collectstatic --noinput --clear

echo "✅ Initialization complete!"

# Start server with debugpy
exec python -Xfrozen_modules=off -m debugpy --listen 0.0.0.0:5678 manage.py runserver 0.0.0.0:8000
