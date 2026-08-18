#!/bin/sh
set -e

echo "Running database migrations..."
until alembic upgrade head; do
  echo "Migration attempt failed (database may not be ready yet) - retrying in 2s..."
  sleep 2
done

echo "Starting application..."
exec "$@"
