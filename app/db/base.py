from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings
# from sqlalchemy import text # For testing connection

# Asynchronous engine
# The 'future=True' flag enables 2.0 style usage now.
# 'echo=True' is useful for debugging SQL queries, remove in production.
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,  # Set to True to see SQL queries
    future=True
)

# Asynchronous session
# expire_on_commit=False prevents attributes from being expired
# after commit, useful in async contexts with FastAPI dependencies.
AsyncSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    future=True
)

Base = declarative_base()

# Dependency to get DB session
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        # Optional: Test connection
        # try:
        #     await session.execute(text("SELECT 1"))
        #     print("Database connection successful.")
        # except Exception as e:
        #     print(f"Database connection failed: {e}")
        #     raise
        yield session