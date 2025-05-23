#!/bin/bash
# Exit immediately if a command exits with a non-zero status.
set -e

echo "INFO: [entrypoint.sh] Starting up..."
echo "INFO: [entrypoint.sh] Current working directory: $(pwd)" # Should be /app

# The alembic.ini file should be in the current working directory (/app)
# if copied correctly by the Dockerfile.
echo "INFO: [entrypoint.sh] Listing contents of current directory:"
ls -la

echo "INFO: [entrypoint.sh] Listing contents of ./alembic directory (if it exists):"
ls -la ./alembic || echo "INFO: ./alembic directory not found."


echo "INFO: [entrypoint.sh] Running database migrations..."
# The `alembic/env.py` script is responsible for constructing the correct
# synchronous database URL from the environment variables provided by Render (DATABASE_URL).
# If alembic.ini is in the current directory (/app), Alembic should find it.
alembic upgrade head
# If alembic upgrade head fails, the `set -e` will cause the script to exit,
# and Render will show a deployment failure, which is correct.

echo "INFO: [entrypoint.sh] Migrations command finished."

# Render provides the PORT environment variable that the application should listen on.
# Fallback to 8000 for local execution if PORT is not set.
APP_PORT=${PORT:-8000}

echo "INFO: [entrypoint.sh] Starting Uvicorn server on port $APP_PORT..."
# Using --workers 1 is often recommended for free/low-resource tiers on PaaS.
# --forwarded-allow-ips='*' is important for running behind Render's proxy.
exec uvicorn app.main:app --host 0.0.0.0 --port "$APP_PORT" --forwarded-allow-ips='*' --workers 1