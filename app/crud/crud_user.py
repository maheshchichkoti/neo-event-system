# app/crud/crud_user.py
from typing import Optional, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.db.models import User # Ensure this is your SQLAlchemy User model
from app.schemas.user import UserCreate # Ensure this is your Pydantic UserCreate schema

class CRUDUser:
    async def get_user_by_id(self, db: AsyncSession, *, user_id: int) -> Optional[User]:
        result = await db.execute(select(User).filter(User.id == user_id))
        return result.scalars().first()

    async def get_user_by_username(self, db: AsyncSession, *, username: str) -> Optional[User]:
        result = await db.execute(select(User).filter(User.username == username))
        return result.scalars().first()

    async def get_user_by_email(self, db: AsyncSession, *, email: str) -> Optional[User]:
        result = await db.execute(select(User).filter(User.email == email))
        return result.scalars().first()

    async def create_user(self, db: AsyncSession, *, user_in: UserCreate) -> User:
        hashed_password = get_password_hash(user_in.password)
        db_user = User(
            username=user_in.username,
            email=user_in.email,
            hashed_password=hashed_password,
            is_active=True 
        )
        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)
        return db_user

    # Add other methods like update_user if needed here
    # async def update_user(self, db: AsyncSession, *, db_user_obj: User, user_in: UserUpdate) -> User:
    # ... implementation ...

user = CRUDUser() # Create an instance of the class