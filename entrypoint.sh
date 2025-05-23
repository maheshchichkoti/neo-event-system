#!/bin/bash
set -e

echo "INFO: Waiting for PostgreSQL to become ready..."

# Wait for PostgreSQL
until pg_isready -h db -U ${POSTGRES_USER} -d ${POSTGRES_DB}; do
  echo "INFO: PostgreSQL not ready yet, sleeping..."
  sleep 2
done

echo "INFO: PostgreSQL is ready. Running migrations..."
alembic upgrade head

echo "INFO: Starting Uvicorn server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --forwarded-allow-ips='*'