# app/db/sync_session.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Automatically fall back if SYNC url not set explicitly
def get_sync_database_url() -> str:
    if settings.DATABASE_URL.startswith("postgresql+asyncpg://"):
        return settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    return settings.DATABASE_URL

sync_engine = create_engine(
    get_sync_database_url(),
    future=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)