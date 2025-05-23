from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.exc import SQLAlchemyError
from app.core.config import settings
import logging

# Configure logging
logger = logging.getLogger(__name__)

# --- Database Engine ---
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # Enable in dev for SQL query logging
    future=True,
    pool_pre_ping=True,  # Checks connection health
    pool_size=20,        # Adjust based on your needs
    max_overflow=10,
    pool_timeout=30,     # Wait 30 sec for connection
    pool_recycle=3600    # Recycle connections after 1 hour
)

# --- Session Factory ---
# Prefer async_sessionmaker over sessionmaker for async
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,  # Critical for async usage
    class_=AsyncSession,
    future=True
)

# --- Declarative Base ---
Base = declarative_base()

# --- Dependency Injection ---
async def get_db() -> AsyncSession:
    """
    Async generator that yields database sessions.
    Ensures sessions are properly closed even if exceptions occur.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()  # Auto-commit if no exceptions
        except SQLAlchemyError as e:
            await session.rollback()
            logger.error(f"Database error occurred: {e}")
            raise
        finally:
            await session.close()  # Explicit close (safety net)

# Optional: Connection test utility
async def check_db_connection():
    """Test database connectivity during startup"""
    try:
        async with AsyncSessionLocal() as session:
            await session.execute("SELECT 1")
        logger.info("Database connection successful")
        return True
    except Exception as e:
        logger.critical(f"Database connection failed: {e}")
        raise