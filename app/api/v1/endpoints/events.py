# app/api/v1/endpoints/events.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Any, Optional, Dict
import datetime
from pydantic import BaseModel 
from deepdiff import DeepDiff # For diffing event versions

from app import schemas # Root for Pydantic schemas
from app import crud    # Root for CRUD operations
from app.db.base import get_db
from app.api.deps import get_current_active_user
from app.db.models import User as DBUser, RoleEnum, Event as DBEvent # SQLAlchemy models
# DBEventPermission import was not strictly needed as perm_orm is typed by inference 
# or direct access to its attributes.

router = APIRouter()

# --- Helper Function ---
def map_event_to_response_schema(db_event: Optional[DBEvent]) -> Optional[schemas.EventWithCurrentVersion]:
    if not db_event:
        # TODO: Log this specific scenario if it's unexpected (e.g., "map_event_to_response_schema called with None db_event")
        return None
    if not db_event.current_version:
        # TODO: Log this specific scenario: event exists but current_version isn't loaded/set
        # (e.g., f"Event ID {db_event.id} is missing current_version for mapping.")
        return None
    
    permissions_response = []
    if db_event.permissions: # Ensure permissions and perm_orm.user were eager-loaded by the CRUD method
        for perm_orm in db_event.permissions:
            user_public_data = None
            if perm_orm.user: # Check if the related user object is loaded
                user_public_data = schemas.UserPublic.model_validate(perm_orm.user)
            
            # Constructing the EventPermission schema instance directly
            permissions_response.append(
                schemas.EventPermission(
                    id=perm_orm.id,
                    event_id=perm_orm.event_id, # This is from the permission ORM object
                    user_id=perm_orm.user_id,
                    role=perm_orm.role,
                    granted_at=perm_orm.granted_at,
                    user=user_public_data # This is the nested UserPublic schema
                )
            )

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

# --- Event CRUD Endpoints ---
@router.post(
    "/", 
    response_model=schemas.EventWithCurrentVersion, 
    status_code=status.HTTP_201_CREATED, 
    summary="Create Event", 
    tags=["Events"]
)
async def create_new_event_endpoint(
    *, 
    db: AsyncSession = Depends(get_db), 
    event_in: schemas.EventCreate, 
    current_user: DBUser = Depends(get_current_active_user)
):
    try:
        created_event_orm = await crud.event.create_event_with_version(
            db=db, event_data=event_in, owner_id=current_user.id
        )
    except ValueError as ve: 
        # TODO: Log ValueError details (e.g., logger.warning(f"Validation error creating event: {ve}", exc_info=True))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        # TODO: Log full error e for internal review (e.g., logger.error("Unexpected error creating event", exc_info=True))
        # import traceback; traceback.print_exc() # For dev only
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="An error occurred while creating the event."
        )
    
    response_data = map_event_to_response_schema(created_event_orm)
    if not response_data:
        # TODO: Log critical error: created_event_orm was None or mapping failed
        # (e.g., logger.error(f"Event created (ORM: {created_event_orm}) but mapping to response failed."))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Event created but failed to prepare response."
        )
    return response_data

@router.get("/{event_id}", response_model=schemas.EventWithCurrentVersion, summary="Get Event", tags=["Events"])
async def get_event_by_id_endpoint(
    *, 
    db: AsyncSession = Depends(get_db), 
    event_id: int, 
    current_user: DBUser = Depends(get_current_active_user)
):
    db_event = await crud.event.get_event_with_details_by_id(db=db, event_id=event_id)
    if not db_event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    
    # Permission check (using crud.permission module)
    user_perm = await crud.permission.get_permission_by_event_and_user(
        db, event_id=event_id, user_id=current_user.id
    )
    if not user_perm: # Any role (Viewer, Editor, Owner) is sufficient to view
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions to view this event")
    
    response_data = map_event_to_response_schema(db_event)
    if not response_data:
         # TODO: Log critical error: mapping failed for existing event
         # (e.g., logger.error(f"Mapping to response failed for event ID {event_id}."))
         raise HTTPException(
             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
             detail="Failed to prepare event data for response."
            )
    return response_data

@router.put("/{event_id}", response_model=schemas.EventWithCurrentVersion, summary="Update Event", tags=["Events"])
async def update_existing_event_endpoint(
    *, 
    db: AsyncSession = Depends(get_db), 
    event_id: int, 
    event_in: schemas.EventUpdate, 
    current_user: DBUser = Depends(get_current_active_user)
):
    db_event_to_update = await crud.event.get_event_with_details_by_id(db=db, event_id=event_id)
    if not db_event_to_update:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    
    user_perm = await crud.permission.get_permission_by_event_and_user(
        db, event_id=event_id, user_id=current_user.id
    )
    if not user_perm or user_perm.role not in [RoleEnum.OWNER, RoleEnum.EDITOR]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions to update this event")
    
    try:
        updated_event_orm = await crud.event.update_event_with_version(
            db=db, event_to_update=db_event_to_update, updates=event_in, user_id=current_user.id
        )
    except ValueError as ve: 
        # TODO: Log ValueError (e.g., logger.warning(f"Validation error updating event {event_id}: {ve}", exc_info=True))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        # TODO: Log full error e (e.g., logger.error(f"Unexpected error updating event {event_id}", exc_info=True))
        # import traceback; traceback.print_exc() # For dev only
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="An error occurred while updating the event."
        )
    
    response_data = map_event_to_response_schema(updated_event_orm)
    if not response_data:
         # TODO: Log critical error: mapping failed after update
         # (e.g., logger.error(f"Event {event_id} updated but mapping to response failed."))
         raise HTTPException(
             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
             detail="Event updated but failed to prepare response."
            )
    return response_data

@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Event", tags=["Events"])
async def delete_existing_event_endpoint(
    *, 
    db: AsyncSession = Depends(get_db), 
    event_id: int, 
    current_user: DBUser = Depends(get_current_active_user)
):
    db_event_to_delete = await crud.event.get_event_with_details_by_id(db=db, event_id=event_id) 
    if not db_event_to_delete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    
    user_perm = await crud.permission.get_permission_by_event_and_user(
        db, event_id=event_id, user_id=current_user.id
    )
    if not user_perm or user_perm.role != RoleEnum.OWNER:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner can delete this event")
    
    try:
        deleted_success = await crud.event.delete_event_by_id(db=db, event_id=event_id)
        if not deleted_success:
            # TODO: Log this unusual scenario (e.g., logger.warning(f"Event {event_id} found but delete_event_by_id reported no rows deleted."))
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event was found but could not be deleted.")
    except Exception as e:
        # TODO: Log full error e (e.g., logger.error(f"Unexpected error deleting event {event_id}", exc_info=True))
        # import traceback; traceback.print_exc() # For dev only
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="An error occurred while deleting the event."
        )
    return 

# Response model for listing events
class EventListResponse(BaseModel): 
    events: List[schemas.EventInstance] 
    total: int
    limit: int
    skip: int

@router.get("/", response_model=EventListResponse, summary="List Events", tags=["Events"])
async def list_events_for_user_endpoint(
    db: AsyncSession = Depends(get_db), 
    current_user: DBUser = Depends(get_current_active_user),
    skip: int = Query(0, ge=0, description="Number of items to skip for pagination"),
    limit: int = Query(100, ge=1, le=200, description="Number of items to return per page"),
    start_time: Optional[datetime.datetime] = Query(None, alias="startTime", description="Filter events occurring after or at this UTC datetime (ISO format)."),
    end_time: Optional[datetime.datetime] = Query(None, alias="endTime", description="Filter events occurring before or at this UTC datetime (ISO format).")
):
    if start_time and start_time.tzinfo is None: 
        start_time = start_time.replace(tzinfo=datetime.timezone.utc)
    if end_time and end_time.tzinfo is None: 
        end_time = end_time.replace(tzinfo=datetime.timezone.utc)
    
    if start_time and end_time and end_time <= start_time:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="endTime must be after startTime.")
    
    try:
        event_instances_data, total_count = await crud.event.get_events_for_user(
            db, 
            user_id=current_user.id, 
            skip=skip, 
            limit=limit,
            filter_start_time=start_time, 
            filter_end_time=end_time
        )
    except Exception as e:
        # TODO: Log full error e (e.g., logger.error(f"Error retrieving events for user {current_user.id}", exc_info=True))
        # import traceback; traceback.print_exc() # For dev only
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error retrieving events.")
    
    try:
        event_instances_schemas = [schemas.EventInstance.model_validate(data) for data in event_instances_data]
    except Exception as e: 
        # TODO: Log full error e (likely Pydantic validation) (e.g., logger.error(f"Error processing event data for user {current_user.id}", exc_info=True))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error processing event data.")
    
    return EventListResponse(events=event_instances_schemas, total=total_count, limit=limit, skip=skip)

@router.post("/batch", response_model=schemas.BatchEventCreateResponse, summary="Batch Create Events", tags=["Events"])
async def create_batch_events_endpoint(
    *, 
    db: AsyncSession = Depends(get_db), 
    batch_request: schemas.BatchEventCreateRequest, 
    current_user: DBUser = Depends(get_current_active_user)
):
    results: List[schemas.EventWithCurrentVersion] = [] 
    # Define errors list based on your updated schemas.BatchEventCreateResponse
    # For example, if it includes `errors: List[schemas.BatchOperationErrorDetail] = []`
    errors_detail: List[schemas.BatchOperationErrorDetail] = []


    for i, event_in_data in enumerate(batch_request.events):
        try:
            created_event_orm = await crud.event.create_event_with_version(
                db=db, event_data=event_in_data, owner_id=current_user.id
            )
            response_data = map_event_to_response_schema(created_event_orm)
            if response_data:
                 results.append(response_data)
            else:
                # This is an internal error if mapping fails after successful ORM creation
                # TODO: Log this internal error (e.g., logger.error(f"Batch Create: Mapping failed for event '{event_in_data.title}' after ORM creation."))
                errors_detail.append(schemas.BatchOperationErrorDetail(
                    index=i, title=event_in_data.title, error="Mapping to response schema failed post-creation."
                ))
        except ValueError as ve: # Validation error from EventCreate or CRUD layer
            # TODO: Log ValueError (e.g., logger.warning(f"Batch Create: Validation error for event '{event_in_data.title}': {ve}", exc_info=True))
            errors_detail.append(schemas.BatchOperationErrorDetail(
                index=i, title=event_in_data.title, error=str(ve)
            ))
        except Exception as e:
            # TODO: Log full error e (e.g., logger.error(f"Batch Create: Unexpected error for event '{event_in_data.title}'", exc_info=True))
            errors_detail.append(schemas.BatchOperationErrorDetail(
                index=i, title=event_in_data.title, error="An unexpected error occurred during creation."
            ))
            
    # Ensure your schemas.BatchEventCreateResponse can handle the 'errors' field.
    # Example: return schemas.BatchEventCreateResponse(results=results, errors=errors_detail)
    # If schema only has 'results':
    if errors_detail:
        # TODO: Log the errors_detail list if not returning it in response
        # (e.g., logger.info(f"Batch event creation completed with errors: {errors_detail}"))
        pass
    return schemas.BatchEventCreateResponse(results=results) # Adjust if schema includes errors

# --- Event Versioning, Changelog, and Diff Endpoints ---

# Moved ChangelogListResponse to be defined locally or imported from schemas if it's global
class ChangelogListResponse(BaseModel): 
    changelog: List[schemas.EventChangeLogEntry]
    total: int
    limit: int
    skip: int

@router.get(
    "/{event_id}/history/{version_id}", 
    response_model=schemas.EventVersion, # Using the existing EventVersion schema
    summary="Get Specific Event Version", 
    tags=["Event Versioning"]
)
async def get_specific_event_version_endpoint(
    event_id: int, 
    version_id: int, 
    db: AsyncSession = Depends(get_db), 
    current_user: DBUser = Depends(get_current_active_user)
):
    event_check = await crud.event.get_event_with_details_by_id(db, event_id=event_id)
    if not event_check: 
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent event not found")
    
    user_perm = await crud.permission.get_permission_by_event_and_user(
        db, event_id=event_id, user_id=current_user.id
    )
    if not user_perm: 
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions to view event history")
    
    db_event_version = await crud.event.get_event_version_by_version_id(
        db, event_id=event_id, version_id=version_id
    )
    if not db_event_version: 
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Specific event version not found")
    
    # Pydantic's schemas.EventVersion will validate and serialize the ORM object
    return db_event_version

@router.post(
    "/{event_id}/rollback/{version_id}", 
    response_model=schemas.EventWithCurrentVersion, 
    summary="Rollback Event to Version", 
    tags=["Event Versioning"]
)
async def rollback_event_to_a_version_endpoint(
    event_id: int, 
    version_id: int, 
    db: AsyncSession = Depends(get_db), 
    current_user: DBUser = Depends(get_current_active_user)
):
    event_to_rollback = await crud.event.get_event_with_details_by_id(db, event_id=event_id)
    if not event_to_rollback: 
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found for rollback")
    
    user_perm = await crud.permission.get_permission_by_event_and_user(
        db, event_id=event_id, user_id=current_user.id
    )
    if not user_perm or user_perm.role not in [RoleEnum.OWNER, RoleEnum.EDITOR]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions to rollback event")
    
    target_version_obj = await crud.event.get_event_version_by_version_id(
        db, event_id=event_id, version_id=version_id
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
        # TODO: Log ValueError (e.g., logger.warning(f"Validation error rolling back event {event_id}: {ve}", exc_info=True))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        # TODO: Log full error e (e.g., logger.error(f"Unexpected error rolling back event {event_id}", exc_info=True))
        # import traceback; traceback.print_exc() # For dev only
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="An error occurred during rollback."
        )
    
    response_data = map_event_to_response_schema(rolled_back_event_orm)
    if not response_data:
         # TODO: Log critical error (e.g., logger.error(f"Event {event_id} rollback successful but mapping to response failed."))
         raise HTTPException(
             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
             detail="Rollback successful but failed to prepare response."
            )
    return response_data

@router.get(
    "/{event_id}/changelog", 
    response_model=ChangelogListResponse, # Uses locally defined or imported ChangelogListResponse
    summary="Get Event Changelog", 
    tags=["Event Versioning"]
)
async def get_event_changelog_endpoint(
    event_id: int, 
    skip: int = Query(0, ge=0), 
    limit: int = Query(100, ge=1, le=200),
    db: AsyncSession = Depends(get_db), 
    current_user: DBUser = Depends(get_current_active_user)
):
    event_check = await crud.event.get_event_with_details_by_id(db, event_id=event_id)
    if not event_check: 
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    
    user_perm = await crud.permission.get_permission_by_event_and_user(
        db, event_id=event_id, user_id=current_user.id
    )
    if not user_perm: 
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions to view changelog")
    
    versions_orm_list, total = await crud.event.get_all_versions_for_event_changelog(
        db, event_id=event_id, skip=skip, limit=limit
    )
    
    try:
        changelog_entries = [schemas.EventChangeLogEntry.model_validate(v_orm) for v_orm in versions_orm_list]
    except Exception as e: 
        # TODO: Log Pydantic validation error or other mapping error 
        # (e.g., logger.error(f"Error processing changelog data for event {event_id}", exc_info=True))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error processing changelog data."
        )
    return ChangelogListResponse(changelog=changelog_entries, total=total, limit=limit, skip=skip)

# Moved EventDiffResponse to be defined locally or imported if global
class EventDiffResponse(BaseModel):
    differences: Dict[str, Any]

@router.get(
    "/{event_id}/diff/{version_id1}/{version_id2}", 
    response_model=EventDiffResponse, 
    summary="Diff Two Event Versions", 
    tags=["Event Versioning"]
)
async def get_event_diff_between_versions_endpoint(
    event_id: int, 
    version_id1: int, 
    version_id2: int,
    db: AsyncSession = Depends(get_db), 
    current_user: DBUser = Depends(get_current_active_user)
):
    if version_id1 == version_id2: 
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot diff a version against itself.")
    
    event_check = await crud.event.get_event_with_details_by_id(db, event_id=event_id)
    if not event_check: 
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent event not found")
    
    user_perm = await crud.permission.get_permission_by_event_and_user(
        db, event_id=event_id, user_id=current_user.id
    )
    if not user_perm: 
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions to view event diff")
    
    version1_orm = await crud.event.get_event_version_by_version_id(db, event_id=event_id, version_id=version_id1)
    version2_orm = await crud.event.get_event_version_by_version_id(db, event_id=event_id, version_id=version_id2)
    
    if not version1_orm or not version2_orm:
        missing_ids = []
        if not version1_orm: missing_ids.append(f"ID {version_id1}")
        if not version2_orm: missing_ids.append(f"ID {version_id2}")
        detail = f"One or both versions not found: {', '.join(missing_ids)}."
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    
    try:
        # Using existing schemas.EventVersion for data extraction
        v1_schema = schemas.EventVersion.model_validate(version1_orm)
        v2_schema = schemas.EventVersion.model_validate(version2_orm)
    except Exception as e: 
        # TODO: Log Pydantic validation error 
        # (e.g., logger.error(f"Error preparing version data for diff, event {event_id}", exc_info=True))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Error preparing version data for diff."
        )
    
    # Fields to exclude from the diff (metadata, not content)
    exclude_from_diff = {'id', 'event_id', 'version_number', 'changed_at', 'changed_by_user_id'}
    
    v1_dict = v1_schema.model_dump(exclude=exclude_from_diff)
    v2_dict = v2_schema.model_dump(exclude=exclude_from_diff)
    
    # ignore_order=True is sensible for lists where order doesn't indicate a change.
    diff_result = DeepDiff(v1_dict, v2_dict, ignore_order=True, verbose_level=0) 
    
    return EventDiffResponse(differences=diff_result.to_dict())