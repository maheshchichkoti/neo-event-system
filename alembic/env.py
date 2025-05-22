# alembic/env.py

import os
import sys
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from pathlib import Path
from dotenv import load_dotenv

# ✅ Find and load .env from *project root* (not /app folder)
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

# --- Project-specific setup ---

# ✅ Add project root to sys.path so Alembic can import app modules
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(PROJECT_ROOT)

# ✅ Import your app's Base (metadata) and models so Alembic sees your tables
from app.db.base import Base
from app.db import models  # This ensures all models are registered

# ✅ App settings (which contain SYNC_DATABASE_URL, etc.)
from app.core.config import settings as app_settings

# --- END setup ---

# ✅ Alembic Config object (reads alembic.ini)
config = context.config

# ✅ Set up Python logging, so you see logs when running Alembic commands
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ✅ SQLAlchemy metadata — needed for Alembic to autogenerate migration scripts
target_metadata = Base.metadata


# ✅ Get the database URL for Alembic to use
def get_url():
    """
    Return the database URL to connect to, either from settings or .ini.
    """
    from pprint import pprint
    sync_db_url = getattr(app_settings, 'SYNC_DATABASE_URL', None)

    pprint(f"✅ SYNC_DATABASE_URL from settings: {sync_db_url}")

    if sync_db_url:
        return sync_db_url

    fallback_url = config.get_main_option("sqlalchemy.url")
    pprint(f"⚠️  Fallback to sqlalchemy.url = {fallback_url}")
    return fallback_url or ""


# ✅ Offline migration configuration
def run_migrations_offline() -> None:
    """
    Run Alembic migrations in 'offline' mode.
    ALEMBIC DOESN'T NEED DB CONNECTION HERE.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,  # Detect type changes
    )

    with context.begin_transaction():
        context.run_migrations()


# ✅ Online migration configuration
def run_migrations_online() -> None:
    """
    Run Alembic migrations in 'online' mode.
    This sets up a SQLAlchemy Engine and connects.
    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # Detect column type changes
        )

        with context.begin_transaction():
            context.run_migrations()


# ✅ Entry point (Alembic will call one of these depending on mode)
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()