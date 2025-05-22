# Use official minimal Python image
FROM python:3.10-slim-buster

# Set working directory
WORKDIR /app

# Prevent .pyc and stdout buffering
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install Poetry
RUN pip install poetry

# Poetry config: disable venv to install in system path (good for Docker)
RUN poetry config virtualenvs.create false

# Copy project configuration
COPY pyproject.toml poetry.lock* ./

# Install dependencies (EXCLUDE dev dependencies)
RUN poetry install --only main --no-root --no-interaction --no-ansi
# Copy actual app code
COPY ./app /app/app

# Run server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]