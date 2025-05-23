# app/crud/crud_permission.py
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete as sqlalchemy_delete, update as sqlalchemy_update, and_
from sqlalchemy.orm import joinedload

from app.db.models import EventPermission, Event, RoleEnum, User
from app.schemas.permission import ShareEventUserPermission # For input type if needed

class CRUDPermission:
    async def get_permission_by_event_and_user(
        self, db: AsyncSession, *, event_id: int, user_id: int
    ) -> Optional[EventPermission]:
        stmt = select(EventPermission).where(
            EventPermission.event_id == event_id,
            EventPermission.user_id == user_id
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def add_permission(
        self, db: AsyncSession, *, event_id: int, user_id: int, role: RoleEnum
    ) -> EventPermission:
        # Check if user exists - using async pattern
        user_stmt = select(User).where(User.id == user_id)
        user_result = await db.execute(user_stmt)
        user_to_share_with = user_result.scalar_one_or_none()
        if not user_to_share_with:
            raise ValueError(f"User with ID {user_id} not found.")
        
        # Check if event exists - using async pattern
        event_stmt = select(Event).where(Event.id == event_id)
        event_result = await db.execute(event_stmt)
        event = event_result.scalar_one_or_none()
        if not event:
            raise ValueError(f"Event with ID {event_id} not found.")

        # Prevent owner from having their role changed via this method or being re-added
        if event.owner_id == user_id and role != RoleEnum.OWNER:
            raise ValueError("Owner's role cannot be changed from OWNER via sharing.")
        if event.owner_id == user_id and role == RoleEnum.OWNER: # Already owner
             existing_perm = await self.get_permission_by_event_and_user(db, event_id=event_id, user_id=user_id)
             if existing_perm: return existing_perm # Should exist

        db_permission = EventPermission(event_id=event_id, user_id=user_id, role=role)
        db.add(db_permission)
        try:
            await db.commit()
            await db.refresh(db_permission)
        except Exception as e: # Catch potential IntegrityError if permission already exists
            await db.rollback()
            # Check if it's because permission already exists
            existing_perm = await self.get_permission_by_event_and_user(db, event_id=event_id, user_id=user_id)
            if existing_perm and existing_perm.role == role: # Already exists with same role
                return existing_perm
            elif existing_perm: # Exists with different role, this should go via update
                raise ValueError(f"User {user_id} already has a permission for event {event_id}. Use PUT to update role.")
            raise e # Re-raise other errors
        return db_permission

    async def get_permissions_for_event(
        self, db: AsyncSession, *, event_id: int
    ) -> List[EventPermission]:
        stmt = select(EventPermission).where(EventPermission.event_id == event_id).options(
            joinedload(EventPermission.user) # Eager load user details
        )
        result = await db.execute(stmt)
        return result.scalars().all()

    async def update_user_permission(
        self, db: AsyncSession, *, event_id: int, user_id: int, new_role: RoleEnum
    ) -> Optional[EventPermission]:
        permission_to_update = await self.get_permission_by_event_and_user(
            db, event_id=event_id, user_id=user_id
        )
        if not permission_to_update:
            return None # Or raise error: "Permission not found"

        # Prevent changing owner's role from OWNER - using async pattern
        event_stmt = select(Event).where(Event.id == event_id)
        event_result = await db.execute(event_stmt)
        event = event_result.scalar_one_or_none()
        if event and event.owner_id == user_id and new_role != RoleEnum.OWNER:
            raise ValueError("Owner's role cannot be changed from OWNER.")

        permission_to_update.role = new_role
        db.add(permission_to_update)
        try:
            await db.commit()
            await db.refresh(permission_to_update)
        except Exception as e:
            await db.rollback()
            raise e
        return permission_to_update

    async def remove_user_permission(
        self, db: AsyncSession, *, event_id: int, user_id: int
    ) -> bool:
        # Prevent removing owner's permission - using async pattern
        event_stmt = select(Event).where(Event.id == event_id)
        event_result = await db.execute(event_stmt)
        event = event_result.scalar_one_or_none()
        if event and event.owner_id == user_id:
            raise ValueError("Owner's permission cannot be removed. To change ownership, a different mechanism would be needed.")

        stmt = sqlalchemy_delete(EventPermission).where(
            EventPermission.event_id == event_id,
            EventPermission.user_id == user_id
        )
        result = await db.execute(stmt)
        try:
            await db.commit()
        except Exception as e:
            await db.rollback()
            raise e
        return result.rowcount > 0

permission = CRUDPermission()