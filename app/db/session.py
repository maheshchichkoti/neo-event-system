# app/db/session.py
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.core.config import settings

# Async engine (for FastAPI)
async_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True
)

# AsyncSession using async_sessionmaker
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False,
)

# Dependency for FastAPI
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session