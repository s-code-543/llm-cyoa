#!/bin/bash
# Entrypoint script for CYOA Game Server container

set -e

echo "🎲 Starting CYOA Game Server..."
mkdir -p /app/db /app/media

# Run migrations (idempotent - safe to run on every startup)
echo "📦 Running migrations..."
python manage.py migrate --noinput

# Collect static files (idempotent - safe to run on every startup)
echo "📂 Collecting static files..."
python manage.py collectstatic --noinput --clear

# Clean up old TTS audio files (uses TTSSettings retention days)
echo "🧹 Cleaning up old TTS audio files..."
python manage.py cleanup_tts_audio

echo "✅ Initialization complete!"

# Compose may select an explicit development or production server command.
if [ "$#" -gt 0 ]; then
    exec "$@"
fi
# Compatibility for existing development deployments.
exec python manage.py runserver 0.0.0.0:8000
