# alembic/env.py

import os
import sys
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool
from pathlib import Path
from dotenv import load_dotenv

# --- Project-specific setup ---

# Add project root to sys.path so Alembic can import app modules
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(PROJECT_ROOT)

# Try to load .env from project root if it exists (useful for local runs)
# For Render, environment variables will be set directly by the platform.
dotenv_path = Path(PROJECT_ROOT) / ".env"
if dotenv_path.exists():
    print(f"Alembic env.py: Loading .env from {dotenv_path}")
    load_dotenv(dotenv_path=dotenv_path)
else:
    print(f"Alembic env.py: .env file not found at {dotenv_path}, relying on system environment variables.")

# Import your app's Base (metadata) and models so Alembic sees your tables
from app.db.base import Base
from app.db import models  # This will register all models
from app.db.sync_session import sync_engine
# Import app settings (which might contain SYNC_DATABASE_URL or DATABASE_URL)
# This needs to happen AFTER potentially loading .env if settings relies on it at import time
try:
    from app.core.config import settings as app_settings
except ImportError:
    app_settings = None 
    print("Warning: app.core.config.settings could not be imported in alembic/env.py. Relying on direct os.environ or alembic.ini.")

# --- END setup ---

# Alembic Config object (reads alembic.ini)
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# SQLAlchemy metadata — needed for Alembic to autogenerate migration scripts
target_metadata = Base.metadata


def get_alembic_db_url():
    """
    Return the synchronous database URL for Alembic.
    Order of precedence:
    1. ALEMBIC_DATABASE_URL environment variable (explicit for migrations).
    2. SYNC_DATABASE_URL from app_settings (if available).
    3. DATABASE_URL from app_settings (converted to sync if async).
    4. DATABASE_URL directly from environment (converted to sync if async) - Render sets this.
    5. SYNC_DATABASE_URL directly from environment.
    6. sqlalchemy.url from alembic.ini (as a final fallback).
    """
    print("Alembic: Determining database URL...")

    # 1. Explicit ALEMBIC_DATABASE_URL (most specific, e.g., for Render migration job)
    alembic_url_env = os.environ.get("ALEMBIC_DATABASE_URL")
    if alembic_url_env:
        print(f"  Using ALEMBIC_DATABASE_URL from environment: {alembic_url_env}")
        return alembic_url_env

    # 2. Try app_settings if available
    if app_settings:
        sync_db_url_settings = getattr(app_settings, 'SYNC_DATABASE_URL', None)
        if sync_db_url_settings:
                if sync_db_url_settings.startswith("postgresql+asyncpg://"):
                    sync_db_url_settings = sync_db_url_settings.replace("postgresql+asyncpg://", "postgresql://")
                    print(f"  Converted SYNC_DATABASE_URL to sync: {sync_db_url_settings}")
                else:
                    print(f"  Using SYNC_DATABASE_URL from app_settings: {sync_db_url_settings}")
                return sync_db_url_settings

        main_db_url_settings = getattr(app_settings, 'DATABASE_URL', None)
        if main_db_url_settings:
            if main_db_url_settings.startswith("postgresql+asyncpg://"):
                sync_url = main_db_url_settings.replace("postgresql+asyncpg://", "postgresql://")
                print(f"  Derived sync URL from app_settings.DATABASE_URL (asyncpg): {sync_url}")
                return sync_url
            elif main_db_url_settings.startswith("postgres://"):
                sync_url = main_db_url_settings.replace("postgres://", "postgresql://")
                print(f"  Derived sync URL from app_settings.DATABASE_URL (postgres://): {sync_url}")
                return sync_url
            elif main_db_url_settings.startswith("postgresql://"):
                print(f"  Using app_settings.DATABASE_URL (already sync): {main_db_url_settings}")
                return main_db_url_settings

    # 3. Try direct environment variables (Render sets DATABASE_URL)
    # This is important if app_settings failed to load or doesn't have the URL.
    main_db_url_env = os.environ.get("DATABASE_URL")
    if main_db_url_env:
        if main_db_url_env.startswith("postgresql+asyncpg://"):
            sync_url = main_db_url_env.replace("postgresql+asyncpg://", "postgresql://")
            print(f"  Derived sync URL from os.environ['DATABASE_URL'] (asyncpg): {sync_url}")
            return sync_url
        elif main_db_url_env.startswith("postgres://"):
            sync_url = main_db_url_env.replace("postgres://", "postgresql://")
            print(f"  Derived sync URL from os.environ['DATABASE_URL'] (postgres://): {sync_url}")
            return sync_url
        elif main_db_url_env.startswith("postgresql://"):
            print(f"  Using os.environ['DATABASE_URL'] (already sync): {main_db_url_env}")
            return main_db_url_env
            
    sync_db_url_env_direct = os.environ.get("SYNC_DATABASE_URL")
    if sync_db_url_env_direct:
        print(f"  Using SYNC_DATABASE_URL from environment: {sync_db_url_env_direct}")
        return sync_db_url_env_direct


    # 4. Fallback to alembic.ini
    ini_url = config.get_main_option("sqlalchemy.url")
    if ini_url:
        print(f"  Falling back to sqlalchemy.url from alembic.ini: {ini_url}")
        return ini_url
    
    print("CRITICAL: Alembic could not determine a database URL. Using a default placeholder which will likely fail.")
    return "postgresql://user:password@localhost/default_db_for_alembic_placeholder"


# Get the effective DB URL once
effective_db_url = get_alembic_db_url()

# You can set it in the config for 'offline' mode or if other parts of env.py read it.
# config.set_main_option("sqlalchemy.url", effective_db_url) # This would modify the config read from alembic.ini

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    print(f"Alembic: Running migrations offline. URL: {effective_db_url}")
    context.configure(
        url=effective_db_url, # Use the resolved URL
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Explicitly use the effective_db_url for the engine configuration.
    # This overrides any sqlalchemy.url that might have been in alembic.ini's [alembic] section.
    engine_config = config.get_section(config.config_ini_section, {})
    if engine_config is None: engine_config = {} # Should not be None but safeguard
    engine_config["sqlalchemy.url"] = effective_db_url
    
    print(f"Alembic: Running migrations online. Connecting to: {effective_db_url}")
    connectable = sync_engine
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True, 
        )
        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()