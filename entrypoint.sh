#!/bin/bash
set -e

echo "INFO: Current directory: $(pwd)"
echo "INFO: Directory contents:"
ls -la

echo "INFO: Running database migrations..."
cd /app && alembic upgrade head

echo "INFO: Starting Uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1