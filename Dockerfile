# Use an official Python runtime as a parent image
FROM python:3.10-slim-buster

# Set environment variables to prevent Python from writing pyc files to disc and buffering output
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies, including postgresql-client (for pg_isready if used in entrypoint)
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry (consider pinning a specific version for reproducibility)
RUN pip install --no-cache-dir poetry==1.7.1 # Or your preferred Poetry version

# Tell Poetry to install packages into the system Python environment (common for Docker)
RUN poetry config virtualenvs.create false

# Copy only the files necessary for poetry to install dependencies
# This leverages Docker's layer caching.
COPY pyproject.toml poetry.lock* ./ 
# The './' here means copy to the current WORKDIR, which is /app

# Install project dependencies using poetry (production dependencies only)
RUN poetry install --only main --no-root --no-interaction --no-ansi

# Copy the rest of the application code and necessary config files
# These paths are relative to the build context (your project root)
# and will be copied into the WORKDIR (/app)
COPY ./alembic ./alembic/      # Copies project_root/alembic to /app/alembic/
COPY ./app ./app/              # Copies project_root/app to /app/app/
COPY alembic.ini ./alembic.ini # Copies project_root/alembic.ini to /app/alembic.ini
COPY entrypoint.sh ./entrypoint.sh # Copies project_root/entrypoint.sh to /app/entrypoint.sh

# Ensure the entrypoint script is executable
RUN chmod +x ./entrypoint.sh

# Expose the port the app runs on (Render uses $PORT, Uvicorn defaults to 8000 if $PORT not set)
EXPOSE 8000 

# Set the entrypoint script to run when the container starts
ENTRYPOINT ["./entrypoint.sh"]