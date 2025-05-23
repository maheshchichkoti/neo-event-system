#!/bin/bash
set -e

# Parse DATABASE_URL (async or sync) to extract host/port/user/db
DB_HOST=$(echo $DATABASE_URL | awk -F'[@/]' '{print $3}' | cut -d':' -f1)
DB_PORT=$(echo $DATABASE_URL | awk -F'[@/]' '{print $3}' | cut -d':' -f2)
DB_USER=$(echo $DATABASE_URL | awk -F'[:@]' '{print $2}')
DB_NAME=$(echo $DATABASE_URL | awk -F'/' '{print $NF}')

# Default to port 5432 if not specified
DB_PORT=${DB_PORT:-5432}

echo "INFO: Waiting for PostgreSQL at $DB_HOST:$DB_PORT..."
until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME"; do
  echo "INFO: PostgreSQL not ready yet, sleeping..."
  sleep 2
done

echo "INFO: Running migrations..."
alembic upgrade head

echo "INFO: Starting Uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000