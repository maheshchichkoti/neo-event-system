# app/api/v1/endpoints/events.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Any, Optional, Dict # Added Dict for DeepDiff output
import datetime
from pydantic import BaseModel 
from deepdiff import DeepDiff # For diffing event versions

from app import schemas # Root for Pydantic schemas
from app import crud    # Root for CRUD operations
from app.db.base import get_db
from app.api.deps import get_current_active_user
from app.db.models import User as DBUser, RoleEnum, Event as DBEvent # SQLAlchemy models

router = APIRouter()

# Helper to map Event ORM object to EventWithCurrentVersion schema
def map_event_to_response_schema(db_event: Optional[DBEvent]) -> Optional[schemas.EventWithCurrentVersion]:
    if not db_event:
        print(f"Warning: map_event_to_response_schema called with None db_event.")
        return None
    if not db_event.current_version:
        # This could happen if the event exists but its current_version was somehow not loaded or set.
        # The crud methods should ensure current_version is loaded.
        print(f"Warning: map_event_to_response_schema: db_event {db_event.id} has no current_version loaded or set.")
        # Depending on strictness, you might raise an error or return a partial response.
        # For now, returning None as the function signature suggests it's possible.
        return None
    
    permissions_response = []
    if db_event.permissions: # Ensure permissions were eager-loaded if you expect them here
        for perm_orm in db_event.permissions:
            user_public_data = None
            if perm_orm.user: # Ensure user was eager-loaded with permission
                user_public_data = schemas.UserPublic(id=perm_orm.user.id, username=perm_orm.user.username)
            
            permissions_response.append(schemas.EventPermissionResponse( # Assuming a specific response schema
                id=perm_orm.id,
                event_id=perm_orm.event_id,
                user_id=perm_orm.user_id,
                role=perm_orm.role,
                granted_at=perm_orm.granted_at,
                user=user_public_data
            ))

    return schemas.EventWithCurrentVersion(
        id=db_event.id,
        owner_id=db_event.owner_id,
        created_at=db_event.created_at,
        # Fields from current_version
        title=db_event.current_version.title,
        description=db_event.current_version.description,
        start_time=db_event.current_version.start_time,
        end_time=db_event.current_version.end_time,
        location=db_event.current_version.location,
        is_recurring=db_event.current_version.is_recurring,
        recurrence_pattern=db_event.current_version.recurrence_pattern,
        # Version specific details from current_version
        version_id=db_event.current_version.id,
        version_number=db_event.current_version.version_number,
        last_changed_at=db_event.current_version.changed_at,
        last_changed_by_user_id=db_event.current_version.changed_by_user_id,
        # Mapped permissions
        permissions=permissions_response
    )

@router.post(
    "/", 
    response_model=schemas.EventWithCurrentVersion, 
    status_code=status.HTTP_201_CREATED,
    summary="Create a New Event",
    tags=["Events"]
)
async def create_new_event(
    *,
    db: AsyncSession = Depends(get_db),
    event_in: schemas.EventCreate,
    current_user: DBUser = Depends(get_current_active_user)
):
    """
    Create a new event. The creator automatically becomes the Owner.
    """
    try:
        created_event_orm = await crud.event.create_event_with_version(
            db=db, event_data=event_in, owner_id=current_user.id
        )
    except ValueError as ve: 
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        # Log the full error internally for debugging
        print(f"Error creating event: {e}") 
        # import traceback; traceback.print_exc() # For dev
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the event."
        )
    
    response_data = map_event_to_response_schema(created_event_orm)
    if not response_data:
        # This indicates an issue after successful creation, possibly in mapping or data integrity.
        print(f"Error: map_event_to_response_schema returned None for created event ORM object: {created_event_orm}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Event created but failed to prepare response due to missing data. Please check server logs."
        )
    return response_data

@router.get(
    "/{event_id}", 
    response_model=schemas.EventWithCurrentVersion,
    summary="Get a Specific Event by ID",
    tags=["Events"]
)
async def get_event_by_id_endpoint(
    *,
    db: AsyncSession = Depends(get_db),
    event_id: int,
    current_user: DBUser = Depends(get_current_active_user)
):
    """
    Retrieve a specific event by its ID.
    User must have at least Viewer permission on the event.
    """
    # Fetch event with all necessary details for mapping and permission checks
    db_event = await crud.event.get_event_with_details_by_id(db=db, event_id=event_id)
    if not db_event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    # Permission check: Current user must have some permission on this event.
    # crud.permission.get_permission_by_event_and_user might be in a different crud file
    user_perm = await crud.event.get_user_permission_for_event(db, event_id=event_id, user_id=current_user.id)
    if not user_perm: # Any role (Viewer, Editor, Owner) is sufficient to view
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions to view this event")

    response_data = map_event_to_response_schema(db_event)
    if not response_data:
         # This should ideally not happen if db_event and its current_version are fine.
         print(f"Error: map_event_to_response_schema returned None for event ID {event_id}")
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to prepare event data for response.")
    return response_data

@router.put(
    "/{event_id}", 
    response_model=schemas.EventWithCurrentVersion,
    summary="Update an Existing Event",
    tags=["Events"]
)
async def update_existing_event(
    *,
    db: AsyncSession = Depends(get_db),
    event_id: int,
    event_in: schemas.EventUpdate, # Pydantic model for update payload
    current_user: DBUser = Depends(get_current_active_user)
):
    """
    Update an existing event. This creates a new version of the event.
    User must be Owner or Editor of the event.
    """
    db_event_to_update = await crud.event.get_event_with_details_by_id(db=db, event_id=event_id)
    if not db_event_to_update:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    user_perm = await crud.event.get_user_permission_for_event(db, event_id=event_id, user_id=current_user.id)
    if not user_perm or user_perm.role not in [RoleEnum.OWNER, RoleEnum.EDITOR]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions to update this event")

    try:
        updated_event_orm = await crud.event.update_event_with_version(
            db=db, event_to_update=db_event_to_update, updates=event_in, user_id=current_user.id
        )
    except ValueError as ve: 
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        print(f"Error updating event {event_id}: {e}")
        # import traceback; traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while updating the event.")
    
    response_data = map_event_to_response_schema(updated_event_orm)
    if not response_data:
         print(f"Error: map_event_to_response_schema returned None after updating event ID {event_id}")
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Event updated but failed to prepare response.")
    return response_data

@router.delete(
    "/{event_id}", 
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an Event",
    tags=["Events"]
)
async def delete_existing_event(
    *,
    db: AsyncSession = Depends(get_db),
    event_id: int,
    current_user: DBUser = Depends(get_current_active_user)
):
    """
    Delete an event. Only the Owner can perform this action.
    All associated versions and permissions will also be deleted due to DB cascade.
    """
    # Fetch to check existence and for permission check (ensures event exists before perm check)
    db_event_to_delete = await crud.event.get_event_with_details_by_id(db=db, event_id=event_id) 
    if not db_event_to_delete:
        # Return 204 even if not found to make it idempotent for DELETE, 
        # or 404 if you prefer strict "must exist" for delete. Common practice varies.
        # For this challenge, 404 is fine if it's not found before permission check.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    user_perm = await crud.event.get_user_permission_for_event(db, event_id=event_id, user_id=current_user.id)
    if not user_perm or user_perm.role != RoleEnum.OWNER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner can delete this event")

    try:
        deleted_success = await crud.event.delete_event_by_id(db=db, event_id=event_id)
        if not deleted_success: 
            # This case implies it was found initially by get_event_with_details_by_id,
            # but delete_event_by_id returned False (e.g. rowcount was 0).
            # This could be a race condition or an unexpected state.
            print(f"Warning: Event {event_id} found but delete_event_by_id reported no rows deleted.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event was found but could not be deleted.")
    except Exception as e:
        print(f"Error deleting event {event_id}: {e}")
        # import traceback; traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred while deleting the event.")
    
    # HTTP 204 No Content means no response body is sent.
    return 

# Response model for listing events (potentially expanded recurring instances)
class EventListResponse(BaseModel): 
    events: List[schemas.EventInstance] # Assumes EventInstance schema exists for expanded items
    total: int
    limit: int
    skip: int

@router.get(
    "/", 
    response_model=EventListResponse,
    summary="List Events Accessible to User",
    tags=["Events"]
)
async def list_events_for_user(
    db: AsyncSession = Depends(get_db),
    current_user: DBUser = Depends(get_current_active_user),
    skip: int = Query(0, ge=0, description="Number of items to skip for pagination"),
    limit: int = Query(100, ge=1, le=200, description="Number of items to return per page"),
    start_time: Optional[datetime.datetime] = Query(None, description="Filter events occurring after or at this UTC datetime (ISO format). For recurring events, this is the start of the expansion window."),
    end_time: Optional[datetime.datetime] = Query(None, description="Filter events occurring before or at this UTC datetime (ISO format). For recurring events, this is the end of the expansion window.")
):
    """
    List all events the current user has access to.
    Supports pagination and filtering by a date range.
    If start_time and end_time are provided, recurring events will be expanded into their instances within this window.
    Otherwise, a paginated list of unique event entities (current versions) is returned.
    """
    # Ensure timezone awareness, defaulting to UTC if naive
    if start_time and start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=datetime.timezone.utc)
    if end_time and end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=datetime.timezone.utc)
    
    # Basic validation for date range
    if start_time and end_time and end_time <= start_time:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="end_time must be after start_time.")

    try:
        event_instances_data, total_count = await crud.event.get_events_for_user(
            db, 
            user_id=current_user.id, 
            skip=skip, 
            limit=limit,
            filter_start_time=start_time, # Pass as filter_start_time
            filter_end_time=end_time     # Pass as filter_end_time
        )
    except Exception as e:
        print(f"Error listing events for user {current_user.id}: {e}")
        # import traceback; traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving events.")

    # Validate data against the EventInstance schema
    # This assumes event_instances_data is a list of dicts suitable for EventInstance
    try:
        event_instances_schemas = [schemas.EventInstance(**data) for data in event_instances_data]
    except Exception as e: # Catch Pydantic validation errors or others
        print(f"Error validating event instance data for user {current_user.id}: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing event data.")

    return EventListResponse(events=event_instances_schemas, total=total_count, limit=limit, skip=skip)


@router.post(
    "/batch", 
    response_model=schemas.BatchEventCreateResponse, # Assumes this schema exists
    summary="Create Multiple Events in Batch",
    tags=["Events"]
)
async def create_batch_events(
    *,
    db: AsyncSession = Depends(get_db),
    batch_request: schemas.BatchEventCreateRequest, # Assumes this schema exists
    current_user: DBUser = Depends(get_current_active_user)
):
    """
    Create multiple events in a single request.
    Each event creation is attempted individually. Failures in one do not stop others.
    The response will indicate successes and potentially failures.
    Note: For true atomicity of the batch, the CRUD layer would need to handle a single transaction.
          This current implementation commits per event via `crud.event.create_event_with_version`.
    """
    # For true atomicity of the batch, the underlying `create_event_with_version` would need to
    # NOT commit itself, and the batch processing function in CRUD would manage a single transaction.
    # The current `crud.event.create_event_with_version` commits per call.
    # This endpoint reflects that by processing one by one.

    results = [] # To store successful schemas.EventWithCurrentVersion
    errors = []  # To store error details for events that failed

    for i, event_in_data in enumerate(batch_request.events):
        try:
            # This will commit each event individually as per current create_event_with_version
            created_event_orm = await crud.event.create_event_with_version(
                db=db, event_data=event_in_data, owner_id=current_user.id
            )
            response_data = map_event_to_response_schema(created_event_orm)
            if response_data:
                 results.append(response_data)
            else:
                # This is an unexpected internal error if creation was successful but mapping failed
                print(f"Batch Create: Successfully created event ORM for '{event_in_data.title}' but mapping to response schema failed.")
                errors.append({"index": i, "title": event_in_data.title, "error": "Mapping to response schema failed post-creation."})
        except ValueError as ve: # Validation error from EventCreate or crud layer
            print(f"Batch Create: Validation error for event '{event_in_data.title}': {ve}")
            errors.append({"index": i, "title": event_in_data.title, "error": str(ve)})
        except Exception as e: # Other unexpected errors during creation
            print(f"Batch Create: Failed to create event '{event_in_data.title}': {e}")
            # import traceback; traceback.print_exc()
            errors.append({"index": i, "title": event_in_data.title, "error": "An unexpected error occurred during creation."})
            
    # Consider if the overall status code should change if there are errors.
    # For now, returning 200 with details.
    return schemas.BatchEventCreateResponse(created_events=results, errors=errors)

# --- Event Versioning, Changelog, and Diff Endpoints ---

@router.get(
    "/{event_id}/history/{version_id}", # Changed from version_identifier for clarity
    response_model=schemas.EventVersionResponse, # Use a specific response schema for EventVersion
    summary="Get a Specific Historical Version of an Event",
    tags=["Event Versioning"]
)
async def get_specific_event_version_endpoint(
    event_id: int,
    version_id: int, # This is EventVersion.id (PK)
    db: AsyncSession = Depends(get_db),
    current_user: DBUser = Depends(get_current_active_user),
):
    """
    Retrieve a specific historical version of an event using the EventVersion's unique ID.
    User must have at least Viewer permission on the parent event.
    """
    # Check if parent event exists and user has permission
    event_check = await crud.event.get_event_with_details_by_id(db, event_id=event_id)
    if not event_check:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent event not found")
    
    # Assuming crud.permission.get_permission_by_event_and_user exists and is appropriate
    user_perm = await crud.event.get_user_permission_for_event(db, event_id=event_id, user_id=current_user.id)
    if not user_perm: # Any role is fine for viewing history
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions to view event history")

    # Fetch the specific version
    db_event_version = await crud.event.get_event_version_by_version_id(
        db, event_id=event_id, version_id=version_id # Pass version_id here
    )
    if not db_event_version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Specific event version not found for this event")
    
    # Map ORM to Pydantic schema (assumes EventVersionResponse exists)
    return schemas.EventVersionResponse.model_validate(db_event_version)

@router.post(
    "/{event_id}/rollback/{version_id}", # Changed from version_identifier
    response_model=schemas.EventWithCurrentVersion,
    summary="Rollback Event to a Previous Version",
    tags=["Event Versioning"]
)
async def rollback_event_to_a_version_endpoint(
    event_id: int,
    version_id: int, # This is EventVersion.id (PK) of the version to roll back TO
    db: AsyncSession = Depends(get_db),
    current_user: DBUser = Depends(get_current_active_user),
):
    """
    Rollback an event to the state of a previous version.
    This creates a *new* version by copying data from the target historical version.
    User must be Owner or Editor of the event.
    """
    event_to_rollback = await crud.event.get_event_with_details_by_id(db, event_id=event_id)
    if not event_to_rollback:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found for rollback")

    user_perm = await crud.event.get_user_permission_for_event(db, event_id=event_id, user_id=current_user.id)
    if not user_perm or user_perm.role not in [RoleEnum.OWNER, RoleEnum.EDITOR]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions to rollback this event")

    target_version_obj = await crud.event.get_event_version_by_version_id(
        db, event_id=event_id, version_id=version_id # Pass version_id here
    )
    if not target_version_obj:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target version for rollback not found")

    try:
        rolled_back_event_orm = await crud.event.rollback_event_to_version(
            db, 
            event_to_rollback=event_to_rollback, 
            target_version_obj=target_version_obj, 
            user_id=current_user.id
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        print(f"Error rolling back event {event_id} to version ID {version_id}: {e}")
        # import traceback; traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An error occurred during rollback.")

    response_data = map_event_to_response_schema(rolled_back_event_orm)
    if not response_data:
         print(f"Error: map_event_to_response_schema returned None after rollback for event ID {event_id}")
         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Rollback successful but failed to prepare response.")
    return response_data


class ChangelogListResponse(BaseModel): # Response model for the changelog list
    changelog: List[schemas.EventChangeLogEntry] # Assumes this schema exists
    total: int
    limit: int
    skip: int

@router.get(
    "/{event_id}/changelog", 
    response_model=ChangelogListResponse,
    summary="Get Event Changelog (Version History)",
    tags=["Event Versioning"]
)
async def get_event_changelog_endpoint(
    event_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: DBUser = Depends(get_current_active_user),
):
    """
    Get a chronological log of all changes (versions) to an event.
    User must have at least Viewer permission on the event.
    Versions are returned oldest first.
    """
    event_check = await crud.event.get_event_with_details_by_id(db, event_id=event_id)
    if not event_check:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    
    user_perm = await crud.event.get_user_permission_for_event(db, event_id=event_id, user_id=current_user.id)
    if not user_perm: 
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions to view event changelog")

    versions_orm_list, total = await crud.event.get_all_versions_for_event_changelog(
        db, event_id=event_id, skip=skip, limit=limit
    )
    
    # Map ORM objects to Pydantic schemas
    # Assumes schemas.EventChangeLogEntry can be created from an EventVersion ORM object
    # and that get_all_versions_for_event_changelog eager loads necessary related data (like changed_by_user).
    changelog_entries = [
        schemas.EventChangeLogEntry.model_validate(version_orm) for version_orm in versions_orm_list
    ]
    return ChangelogListResponse(changelog=changelog_entries, total=total, limit=limit, skip=skip)


class EventDiffResponse(BaseModel): # Explicit response model for diff
    differences: Dict[str, Any] # DeepDiff output is a dictionary

@router.get(
    "/{event_id}/diff/{version_id1}/{version_id2}", 
    response_model=EventDiffResponse, # Use the new response model
    summary="Get Diff Between Two Event Versions",
    tags=["Event Versioning"]
)
async def get_event_diff_between_versions_endpoint(
    event_id: int,
    version_id1: int, # EventVersion.id (PK) of the first version
    version_id2: int, # EventVersion.id (PK) of the second version
    db: AsyncSession = Depends(get_db),
    current_user: DBUser = Depends(get_current_active_user),
):
    """
    Get a detailed difference between two specified versions of an event.
    User must have at least Viewer permission on the event.
    The diff shows changes from version_id1 to version_id2.
    """
    if version_id1 == version_id2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot diff a version against itself.")

    # Check parent event and user permission
    event_check = await crud.event.get_event_with_details_by_id(db, event_id=event_id)
    if not event_check:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent event not found")
    
    user_perm = await crud.event.get_user_permission_for_event(db, event_id=event_id, user_id=current_user.id)
    if not user_perm: 
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions to view event diff")

    # Fetch both versions
    version1_orm = await crud.event.get_event_version_by_version_id(db, event_id=event_id, version_id=version_id1)
    version2_orm = await crud.event.get_event_version_by_version_id(db, event_id=event_id, version_id=version_id2)

    if not version1_orm or not version2_orm:
        missing_versions = []
        if not version1_orm: missing_versions.append(f"version ID {version_id1}")
        if not version2_orm: missing_versions.append(f"version ID {version_id2}")
        detail = f"One or both event versions not found for this event: {', '.join(missing_versions)}."
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)

    # For a consistent diff (changes from "old" to "new"), ensure version1_orm is older.
    # If not, swap them for diffing, but the API path implies user specifies order.
    # We'll diff them as provided by version_id1 and version_id2.
    # The user should ideally provide the older version as version_id1.
    # You could add a check: if version1_orm.version_number > version2_orm.version_number: swap them internally.

    # Convert ORM objects to Pydantic models, then to dicts for DeepDiff.
    # Exclude metadata fields that are not part of the versioned "data content".
    # This should align with the fields your EventVersionResponse or similar Pydantic schema exposes.
    # A common Pydantic model for "EventVersionData" could be useful here.
    
    # Assuming you have a Pydantic schema like schemas.EventVersionData that represents the
    # core data fields of an event version (title, description, start_time, etc.)
    try:
        # Validate ORM objects against a schema that represents the core data
        # This helps ensure we are diffing comparable structures.
        # If you have a schemas.EventVersionData or similar:
        # v1_data_schema = schemas.EventVersionData.model_validate(version1_orm)
        # v2_data_schema = schemas.EventVersionData.model_validate(version2_orm)
        
        # For now, let's assume your main schemas.EventVersionResponse can be used,
        # and we'll dump it to dict and then exclude.
        v1_schema = schemas.EventVersionResponse.model_validate(version1_orm)
        v2_schema = schemas.EventVersionResponse.model_validate(version2_orm)
    except Exception as e: # Pydantic validation error
        print(f"Error validating version ORM objects to Pydantic schemas for diff: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error preparing version data for diff.")

    # Define fields to exclude from the diff (metadata, not content)
    exclude_from_diff = {'id', 'event_id', 'version_number', 'changed_at', 'changed_by_user_id', 'changed_by_user'} 
                            # Add 'changed_by_user' if it's a nested Pydantic model you don't want to diff.

    v1_dict = v1_schema.model_dump(exclude=exclude_from_diff)
    v2_dict = v2_schema.model_dump(exclude=exclude_from_diff)
    
    # ignore_order=True can be useful for lists where item order doesn't signify a change.
    # view='text' gives a human-readable string diff. Default (dict) is better for APIs.
    # verbose_level=0 (default) only shows additions, removals, changes.
    # verbose_level=1 also shows type changes.
    # verbose_level=2 can be very verbose for lists.
    diff_result = DeepDiff(v1_dict, v2_dict, ignore_order=False, verbose_level=0) 
    
    return EventDiffResponse(differences=diff_result.to_dict()) # DeepDiff object has a to_dict() method