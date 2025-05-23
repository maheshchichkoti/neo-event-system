# app/api/v1/endpoints/collaboration.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app import schemas, crud
from app.db.session import get_db
from app.api.deps import get_current_active_user
from app.db.models import User as DBUser, RoleEnum, Event as DBEvent # Import DBEvent for type hint

router = APIRouter()

# Helper to check if user has at least a certain level of permission
async def _get_event_and_check_permission(
    db: AsyncSession, event_id: int, user_id: int, allowed_roles: List[RoleEnum]
) -> DBEvent: # Returns the DBEvent object if permitted
    event = await crud.event.get_event_with_details_by_id(db=db, event_id=event_id)
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    
    user_perm = await crud.permission.get_permission_by_event_and_user(db, event_id=event_id, user_id=user_id)
    if not user_perm or user_perm.role not in allowed_roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions for this action")
    return event


@router.post(
    "/events/{event_id}/share", 
    response_model=List[schemas.EventPermission], # Returns the list of all permissions for the event
    status_code=status.HTTP_200_OK # Or 201 if creating new permissions
)
async def share_event_with_users(
    event_id: int,
    share_request: schemas.ShareEventRequest,
    db: AsyncSession = Depends(get_db),
    current_user: DBUser = Depends(get_current_active_user),
):
    """ Share an event with other users. Current user must be Owner or Editor. """
    await _get_event_and_check_permission(db, event_id, current_user.id, [RoleEnum.OWNER, RoleEnum.EDITOR])

    # Prevent sharing with OWNER role if not the original owner doing it for themselves (which is redundant)
    for user_perm_request in share_request.users:
        if user_perm_request.role == RoleEnum.OWNER:
            event_check = await db.get(DBEvent, event_id)
            if not event_check or event_check.owner_id != user_perm_request.user_id:
                 raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot assign OWNER role to another user via sharing.")
    
    results = []
    for user_perm_to_add in share_request.users:
        try:
            # Check if permission already exists, if so, update it
            existing_perm = await crud.permission.get_permission_by_event_and_user(
                db, event_id=event_id, user_id=user_perm_to_add.user_id
            )
            if existing_perm:
                # If user already has permission, treat this as an update
                # Ensure user being updated is not the owner if trying to change owner's role
                event_details = await db.get(DBEvent, event_id)
                if event_details and event_details.owner_id == user_perm_to_add.user_id and user_perm_to_add.role != RoleEnum.OWNER:
                     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Owner's role cannot be changed from OWNER.")
                
                updated_perm = await crud.permission.update_user_permission(
                    db, event_id=event_id, user_id=user_perm_to_add.user_id, new_role=user_perm_to_add.role
                )
                if updated_perm: results.append(updated_perm) # Should exist
            else:
                # Add new permission
                new_perm = await crud.permission.add_permission(
                    db, event_id=event_id, user_id=user_perm_to_add.user_id, role=user_perm_to_add.role
                )
                results.append(new_perm)
        except ValueError as ve: # Catch ValueErrors from CRUD (e.g., user not found)
            # Log this error, maybe return a partial success with error details
            print(f"Error sharing event {event_id} with user {user_perm_to_add.user_id}: {ve}")
            # For now, we skip adding this to results on error
        except Exception as e:
            print(f"Generic error sharing event {event_id} with user {user_perm_to_add.user_id}: {e}")
            # Skip or add error marker
    
    # Fetch all current permissions to return the updated list
    all_permissions = await crud.permission.get_permissions_for_event(db, event_id=event_id)
    return all_permissions


@router.get("/events/{event_id}/permissions", response_model=List[schemas.EventPermission])
async def list_event_permissions(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: DBUser = Depends(get_current_active_user),
):
    """ List all permissions for an event. Current user must have at least Viewer permission. """
    await _get_event_and_check_permission(db, event_id, current_user.id, [RoleEnum.OWNER, RoleEnum.EDITOR, RoleEnum.VIEWER])
    
    permissions = await crud.permission.get_permissions_for_event(db, event_id=event_id)
    return permissions


@router.put("/events/{event_id}/permissions/{user_id_to_update}", response_model=schemas.EventPermission)
async def update_user_event_permission(
    event_id: int,
    user_id_to_update: int, # User whose permission is being changed
    permission_update: schemas.EventPermissionUpdate, # Contains the new role
    db: AsyncSession = Depends(get_db),
    current_user: DBUser = Depends(get_current_active_user), # User performing the action
):
    """ Update a user's permission for an event. Current user must be Owner or Editor. """
    await _get_event_and_check_permission(db, event_id, current_user.id, [RoleEnum.OWNER, RoleEnum.EDITOR])

    # Prevent assigning OWNER role to someone else if current_user is not the actual owner,
    # or if trying to demote original owner.
    event_details = await db.get(DBEvent, event_id)
    if not event_details: # Should be caught by _get_event_and_check_permission
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    if permission_update.role == RoleEnum.OWNER and event_details.owner_id != user_id_to_update:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot make another user an OWNER via this endpoint.")
    if event_details.owner_id == user_id_to_update and permission_update.role != RoleEnum.OWNER:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Original owner's role cannot be changed from OWNER.")

    try:
        updated_permission = await crud.permission.update_user_permission(
            db, event_id=event_id, user_id=user_id_to_update, new_role=permission_update.role
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))

    if not updated_permission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permission entry not found for this user and event.")
    
    # Need to load the user for the response schema
    await db.refresh(updated_permission, attribute_names=['user'])
    return updated_permission


@router.delete("/events/{event_id}/permissions/{user_id_to_remove}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_user_access_to_event(
    event_id: int,
    user_id_to_remove: int,
    db: AsyncSession = Depends(get_db),
    current_user: DBUser = Depends(get_current_active_user),
):
    """ Remove a user's access to an event. Current user must be Owner or Editor. """
    event_details = await _get_event_and_check_permission(db, event_id, current_user.id, [RoleEnum.OWNER, RoleEnum.EDITOR])

    # Prevent removing the original owner
    if event_details.owner_id == user_id_to_remove:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove the event owner's permission.")
    
    # Ensure current user is not trying to remove themselves if they are an editor but not owner
    if current_user.id == user_id_to_remove and event_details.owner_id != current_user.id:
         raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Editors cannot remove their own permissions; ask an Owner.")

    try:
        deleted = await crud.permission.remove_user_permission(db, event_id=event_id, user_id=user_id_to_remove)
    except ValueError as ve: # Catches "Owner's permission cannot be removed" from CRUD
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
        
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Permission entry not found for this user and event, or deletion failed.")
    return