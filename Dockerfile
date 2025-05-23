FROM python:3.10-slim-buster

WORKDIR /app # Set working directory first

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry==1.7.1 
RUN poetry config virtualenvs.create false

COPY pyproject.toml poetry.lock* ./

RUN poetry install --only main --no-root --no-interaction --no-ansi

# Copy application code AND alembic.ini
COPY ./alembic /app/alembic     # Alembic scripts and env.py
COPY ./app /app/app             # Your main application Python code
COPY alembic.ini /app/alembic.ini # **** ADD THIS LINE to copy alembic.ini to /app ****

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000 
ENTRYPOINT ["/app/entrypoint.sh"]