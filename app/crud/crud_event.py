# app/crud/crud_event.py
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update as sqlalchemy_update, delete as sqlalchemy_delete, and_, or_, func
from sqlalchemy.orm import joinedload, selectinload, aliased
from sqlalchemy.exc import SQLAlchemyError, NoResultFound

from app.db.models import Event, EventVersion, User, EventPermission, RoleEnum
from app.schemas.event import EventCreate, EventUpdate # Assuming schemas.event has EventVersion too
import datetime # For date range filtering if needed

# For recurring event expansion
from dateutil import rrule
from dateutil.parser import isoparse


class CRUDEvent:
    async def create_event_with_version(
        self, db: AsyncSession, *, event_data: EventCreate, owner_id: int
    ) -> Optional[Event]:
        db_event_version = EventVersion(
            title=event_data.title, description=event_data.description,
            start_time=event_data.start_time, end_time=event_data.end_time,
            location=event_data.location, is_recurring=event_data.is_recurring,
            recurrence_pattern=event_data.recurrence_pattern, version_number=1,
            changed_by_user_id=owner_id
        )
        db_event = Event(owner_id=owner_id)
        db_event_version.event_parent = db_event # Assumes 'event_parent' is a relationship name
        db.add_all([db_event, db_event_version])

        try:
            await db.flush()
            if db_event.id is None or db_event_version.id is None:
                # Consider using proper logging instead of print for production
                print(f"CRITICAL: ID not generated for Event or EventVersion after flush. Event data: {event_data}, Owner: {owner_id}")
                raise RuntimeError("Event or EventVersion ID generation failed.") # More specific exception
            
            # Ensure FK is set if not done by backref/back_populates (belt and suspenders)
            if db_event_version.event_id is None: # Check if relationship didn't set it
                 db_event_version.event_id = db_event.id
            
            db_event.current_version_id = db_event_version.id
            
            owner_permission = EventPermission(
                event_id=db_event.id, user_id=owner_id, role=RoleEnum.OWNER
            )
            db.add(owner_permission)
            await db.commit()
        except Exception as e: # Catch SQLAlchemyError or more specific DB errors if possible
            await db.rollback()
            # Log the exception
            print(f"Error during event/version/permission creation, transaction rolled back: {e}")
            raise # Re-raise the original exception or a custom one

        # Re-fetch to get all eager-loaded fields correctly populated from DB state
        refreshed_event_stmt = (
            select(Event).where(Event.id == db_event.id)
            .options(
                joinedload(Event.current_version),
                joinedload(Event.owner),
                selectinload(Event.permissions).joinedload(EventPermission.user) # Use selectinload for collections
            )
        )
        result = await db.execute(refreshed_event_stmt)
        # .unique() is not strictly needed here if Event.id is PK and no collection based joinedloads cause cartesian product
        final_event = result.scalars().one_or_none()
        if final_event is None:
            # Log critical error
            print(f"CRITICAL: Event with ID {db_event.id} could not be re-fetched after successful commit.")
            raise RuntimeError(f"Failed to re-fetch created event {db_event.id}")
        return final_event

    async def get_event_with_details_by_id(
        self, db: AsyncSession, *, event_id: int
    ) -> Optional[Event]:
        """ Gets a single event by ID, eager loading details for response. """
        stmt = (
            select(Event)
            .where(Event.id == event_id)
            .options(
                joinedload(Event.current_version),
                joinedload(Event.owner),
                selectinload(Event.permissions).joinedload(EventPermission.user)
            )
        )
        result = await db.execute(stmt)
        return result.scalars().one_or_none()

    async def get_user_permission_for_event(
        self, db: AsyncSession, *, event_id: int, user_id: int
    ) -> Optional[EventPermission]:
        """ Gets a specific user's permission for a given event. """
        stmt = select(EventPermission).where(
            EventPermission.event_id == event_id,
            EventPermission.user_id == user_id
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def update_event_with_version(
        self, db: AsyncSession, *, event_to_update: Event, updates: EventUpdate, user_id: int
    ) -> Optional[Event]:
        """ Updates an event by creating a new EventVersion. """
        if not event_to_update.current_version:
            # This indicates an issue with how event_to_update was loaded or state corruption
            # Log error
            raise ValueError("Event to update has no current version loaded.")

        current_data = event_to_update.current_version
        
        # Initialize new_version_data with all fields from current_data
        new_version_data = {
            field.name: getattr(current_data, field.name)
            for field in EventVersion.__table__.columns # A more robust way to get all fields
            if field.name not in ['id', 'event_id', 'version_number', 'changed_at', 'changed_by_user_id'] # Exclude meta fields
        }
        # Or manually, if EventVersion fields are stable:
        # new_version_data = {
        #     "title": current_data.title, "description": current_data.description,
        #     "start_time": current_data.start_time, "end_time": current_data.end_time,
        #     "location": current_data.location, "is_recurring": current_data.is_recurring,
        #     "recurrence_pattern": current_data.recurrence_pattern,
        # }
        
        update_data_dict = updates.model_dump(exclude_unset=True)
        if not update_data_dict: 
            return event_to_update # No changes provided

        has_changes = False
        for field, value in update_data_dict.items():
            if field in new_version_data: # Ensure field is one we manage
                if new_version_data[field] != value:
                    has_changes = True
                new_version_data[field] = value
            # else: field from updates is not in EventVersion's user-editable data, could log a warning
        
        if not has_changes: 
             return event_to_update # Data provided matched existing data

        # Validations on the final new_version_data
        if new_version_data.get("is_recurring") and not new_version_data.get("recurrence_pattern"):
            raise ValueError("recurrence_pattern is required if event is recurring.")
        if new_version_data.get("is_recurring") is False and new_version_data.get("recurrence_pattern") is not None:
            raise ValueError("recurrence_pattern must be null if event is not recurring.")
        if new_version_data.get("start_time") and new_version_data.get("end_time") and \
           new_version_data["end_time"] <= new_version_data["start_time"]:
            raise ValueError("end_time must be after start_time.")

        new_db_version = EventVersion(
            event_id=event_to_update.id,
            version_number=current_data.version_number + 1,
            changed_by_user_id=user_id,
            **new_version_data # Unpack the collected data
        )
        db.add(new_db_version)
        try:
            await db.flush() 
            if new_db_version.id is None:
                # Log critical
                raise RuntimeError("New EventVersion ID not generated after flush.")

            event_to_update.current_version_id = new_db_version.id
            await db.commit()
        except Exception as e:
            await db.rollback()
            # Log exception
            raise
        
        # Re-fetch for consistency, ensuring the caller gets the DB state
        return await self.get_event_with_details_by_id(db, event_id=event_to_update.id)

    async def delete_event_by_id(self, db: AsyncSession, *, event_id: int) -> bool:
        """ Deletes an event by its ID. Returns True if deleted, False otherwise. """
        # Consider if fetching before delete is necessary. Direct delete can be more performant.
        # However, checking existence first can provide a clearer 404 if it doesn't exist.
        # Here, if it's called after an auth check that confirms event exists, direct delete is fine.
        stmt = sqlalchemy_delete(Event).where(Event.id == event_id)
        result = await db.execute(stmt)
        try:
            await db.commit()
        except Exception as e:
            await db.rollback()
            # Log exception
            raise
        return result.rowcount > 0

    def _expand_recurring_event(
        self, 
        event_version_data: dict,
        filter_start_time: datetime.datetime, 
        filter_end_time: datetime.datetime
    ) -> List[Dict[str, Any]]:
        """ Expands a recurring event into instances within the filter range. """
        instances = []
        # Ensure start_time and end_time are datetime objects
        ev_start_dt = event_version_data["start_time"]
        ev_end_dt = event_version_data["end_time"]

        if not isinstance(ev_start_dt, datetime.datetime) or not isinstance(ev_end_dt, datetime.datetime):
            # Log error: Unexpected type for start/end time
            # This might happen if event_version_data comes from a raw dict not validated Pydantic model
            print(f"Warning: start_time or end_time not datetime objects for event data: {event_version_data.get('title')}")
            return []


        if not event_version_data.get("is_recurring") or not event_version_data.get("recurrence_pattern"):
            if ev_start_dt < filter_end_time and ev_end_dt > filter_start_time:
                instances.append({
                    "title": event_version_data["title"],
                    "instance_start_time": ev_start_dt,
                    "instance_end_time": ev_end_dt,
                    "location": event_version_data.get("location"),
                    # "original_event_id": event_version_data.get("event_id") # If needed
                })
            return instances

        try:
            dtstart = ev_start_dt
            # Timezone handling: Crucial! Assume UTC if not specified, or ensure consistency.
            # If filter_start_time is aware, dtstart should also be aware.
            if dtstart.tzinfo is None and filter_start_time.tzinfo is not None:
                 dtstart = dtstart.replace(tzinfo=datetime.timezone.utc) # Default to UTC or app's standard TZ
            # Ensure filter times are also consistently handled (e.g., converted to UTC) before this function
            
            event_duration = ev_end_dt - ev_start_dt
            
            rule = rrule.rrulestr(event_version_data["recurrence_pattern"], dtstart=dtstart)

            for occurrence_start in rule.between(filter_start_time, filter_end_time, inc=True):
                # Ensure occurrence_start is timezone-aware if rule generates naive and filters are aware
                if occurrence_start.tzinfo is None and filter_start_time.tzinfo is not None:
                    occurrence_start = occurrence_start.replace(tzinfo=filter_start_time.tzinfo) # Align with filter's TZ

                occurrence_end = occurrence_start + event_duration
                if occurrence_start < filter_end_time and occurrence_end > filter_start_time:
                    instances.append({
                        "title": event_version_data["title"],
                        "instance_start_time": occurrence_start,
                        "instance_end_time": occurrence_end,
                        "location": event_version_data.get("location"),
                        # "original_event_id": event_version_data.get("event_id")
                    })
        except Exception as e:
            # Log error expanding recurring event
            print(f"Error expanding recurring event (title: {event_version_data.get('title')}): {e}")
        return instances

    async def get_events_for_user(
        self, 
        db: AsyncSession, 
        *, 
        user_id: int, 
        skip: int = 0, 
        limit: int = 100,
        filter_start_time: Optional[datetime.datetime] = None,
        filter_end_time: Optional[datetime.datetime] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        CurrentEventVersion = aliased(EventVersion)
        
        base_query = (
            select(Event, CurrentEventVersion)
            .join(Event.permissions)
            .join(CurrentEventVersion, Event.current_version_id == CurrentEventVersion.id)
            .where(EventPermission.user_id == user_id)
        )
        
        if not filter_start_time or not filter_end_time:
            # Path for non-date-filtered, paginated list of unique events
            count_query = select(func.count(Event.id.distinct())).select_from(base_query.alias("subquery_for_count"))
            total_count_result = await db.execute(count_query)
            total = total_count_result.scalar_one()

            paginated_query = base_query.order_by(CurrentEventVersion.start_time).offset(skip).limit(limit)
            db_events_with_versions = await db.execute(paginated_query)
            
            results = []
            for event_obj, version_obj in db_events_with_versions.unique().all(): # .unique() needed if joins created duplicates
                results.append({
                    "event_id": event_obj.id, # Crucial for client to identify the event
                    "title": version_obj.title,
                    "instance_start_time": version_obj.start_time, # For non-recurring, this is the actual start
                    "instance_end_time": version_obj.end_time,
                    "location": version_obj.location,
                    "is_recurring": version_obj.is_recurring, # Useful for client
                    # Add other fields from version_obj as needed by your response schema
                })
            return results, total

        # Path for date-filtered list, potentially with expanded recurring events
        # Pre-filter candidates in DB as much as possible
        candidate_query = base_query.where(
            or_(
                CurrentEventVersion.is_recurring == True,
                and_(
                    CurrentEventVersion.is_recurring == False,
                    CurrentEventVersion.end_time >= filter_start_time,
                    CurrentEventVersion.start_time <= filter_end_time
                )
            )
        )
        
        candidate_events_results = await db.execute(candidate_query)
        
        all_instances: List[Dict[str, Any]] = []
        # Use .unique().all() if there's a chance of duplicate (Event, CurrentEventVersion) tuples from joins
        for event_obj, version_obj in candidate_events_results.unique().all(): 
            # Convert ORM object to dict for _expand_recurring_event
            # Ideally, use a Pydantic model for this structure if complex
            version_data = {
                "event_id": event_obj.id, # Pass original event ID
                "title": version_obj.title, "description": version_obj.description,
                "start_time": version_obj.start_time, "end_time": version_obj.end_time,
                "location": version_obj.location, "is_recurring": version_obj.is_recurring,
                "recurrence_pattern": version_obj.recurrence_pattern,
            }
            expanded_instances = self._expand_recurring_event(version_data, filter_start_time, filter_end_time)
            # Ensure original event_id is part of each instance
            for inst in expanded_instances:
                inst["original_event_id"] = event_obj.id # or "event_id"
            all_instances.extend(expanded_instances)

        all_instances.sort(key=lambda x: x["instance_start_time"])
        
        total = len(all_instances)
        paginated_instances = all_instances[skip : skip + limit]
        
        return paginated_instances, total

    async def get_event_version_by_version_id(
        self, db: AsyncSession, *, event_id: int, version_id: int
    ) -> Optional[EventVersion]:
        stmt = select(EventVersion).where(
            EventVersion.id == version_id,
            EventVersion.event_id == event_id
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def get_event_version_by_version_number(
        self, db: AsyncSession, *, event_id: int, version_number: int
    ) -> Optional[EventVersion]:
        stmt = select(EventVersion).where(
            EventVersion.event_id == event_id,
            EventVersion.version_number == version_number
        )
        result = await db.execute(stmt)
        return result.scalars().first()

    async def get_all_versions_for_event(
        self, db: AsyncSession, *, event_id: int, skip: int = 0, limit: int = 100
    ) -> Tuple[List[EventVersion], int]:
        """ Fetches all versions for a given event, ordered by version_number descending (latest first). """
        count_stmt = select(func.count(EventVersion.id)).where(EventVersion.event_id == event_id)
        total_count_res = await db.execute(count_stmt)
        total = total_count_res.scalar_one_or_none() or 0

        stmt = (
            select(EventVersion)
            .where(EventVersion.event_id == event_id)
            .order_by(EventVersion.version_number.desc()) # Latest version first
            .options(joinedload(EventVersion.changed_by_user).load_only(User.username)) # Example of loading user
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        versions = result.scalars().all()
        return versions, total

    # **** NEW METHOD FOR CHANGELOG ****
    async def get_all_versions_for_event_changelog(
        self, db: AsyncSession, *, event_id: int, skip: int = 0, limit: int = 100
    ) -> Tuple[List[EventVersion], int]:
        """ Fetches all versions for a given event, ordered for changelog (ascending version number - oldest first). """
        count_stmt = select(func.count(EventVersion.id)).where(EventVersion.event_id == event_id)
        total_count_res = await db.execute(count_stmt)
        total = total_count_res.scalar_one_or_none() or 0 # Ensure total is 0 if None

        stmt = (
            select(EventVersion)
            .where(EventVersion.event_id == event_id)
            .order_by(EventVersion.version_number.asc()) # Ascending for changelog (oldest first)
            .options(joinedload(EventVersion.changed_by_user).load_only(User.username, User.id)) # Load relevant user details
            .offset(skip)
            .limit(limit)
        )
        result = await db.execute(stmt)
        versions = result.scalars().all()
        return versions, total
    # **** END OF NEW METHOD ****

    async def rollback_event_to_version(
        self, 
        db: AsyncSession, 
        *, 
        event_to_rollback: Event,
        target_version_obj: EventVersion,
        user_id: int
    ) -> Optional[Event]:
        if not event_to_rollback.current_version:
            # Log error
            raise ValueError("Event to rollback has no current version details loaded.")
        if target_version_obj.event_id != event_to_rollback.id:
            # Log error
            raise ValueError("Target version does not belong to the specified event.")

        current_latest_version_number = event_to_rollback.current_version.version_number

        rolled_back_version = EventVersion(
            event_id=event_to_rollback.id,
            version_number=current_latest_version_number + 1,
            changed_by_user_id=user_id,
            title=target_version_obj.title,
            description=target_version_obj.description,
            start_time=target_version_obj.start_time,
            end_time=target_version_obj.end_time,
            location=target_version_obj.location,
            is_recurring=target_version_obj.is_recurring,
            recurrence_pattern=target_version_obj.recurrence_pattern
        )
        db.add(rolled_back_version)
        try:
            await db.flush()
            if rolled_back_version.id is None:
                # Log critical
                raise RuntimeError("Rolled-back EventVersion ID not generated after flush.")

            event_to_rollback.current_version_id = rolled_back_version.id
            await db.commit()
        except Exception as e:
            await db.rollback()
            # Log exception
            raise

        return await self.get_event_with_details_by_id(db, event_id=event_to_rollback.id)

event = CRUDEvent()