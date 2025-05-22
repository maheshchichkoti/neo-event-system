from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # For FastAPI async
    DATABASE_URL: str  # e.g., postgresql+asyncpg://...

    # For Alembic sync
    SYNC_DATABASE_URL: Optional[str] = None  # postgresql://...

    # JWT & others
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Pydantic v2-style config
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()


# Global instance (used in Alembic or app)
settings = get_settings()