#!/bin/sh
set -e

echo "Waiting for database..."
# Retry alembic up to 10 times with 3s delay — handles Render cold-start timing
attempt=0
until alembic upgrade head; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 10 ]; then
    echo "Database migration failed after $attempt attempts"
    exit 1
  fi
  echo "Migration attempt $attempt failed — retrying in 3s..."
  sleep 3
done
echo "Migrations complete."

exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
