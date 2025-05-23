#!/bin/bash
set -e # Exit immediately if a command exits with a non-zero status.

echo "INFO: [entrypoint.sh] Starting up..."

# On Render, we assume the DATABASE_URL environment variable is correctly set
# by the platform and points to an available database.
# Alembic will attempt to connect using the URL derived in alembic/env.py.
# If the database is not ready, Alembic will fail, causing the deployment to fail,
# which is the desired behavior (fail fast).

echo "INFO: [entrypoint.sh] Running database migrations..."
# The alembic/env.py script is responsible for constructing the correct
# synchronous database URL from the environment variables provided by Render.
alembic upgrade head

echo "INFO: [entrypoint.sh] Migrations command finished."

# Render provides the PORT environment variable that the application should listen on.
# Fallback to 8000 for local execution if PORT is not set.
APP_PORT=${PORT:-8000}

echo "INFO: [entrypoint.sh] Starting Uvicorn server on port $APP_PORT..."
exec uvicorn app.main:app --host 0.0.0.0 --port "$APP_PORT" --forwarded-allow-ips='*' --workers 1