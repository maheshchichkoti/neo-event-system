# app/schemas/permission.py
from pydantic import BaseModel, Field
from typing import List, Optional
import datetime
from app.db.models import RoleEnum

# Forward reference for UserPublic
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .user import UserPublic

class EventPermissionBase(BaseModel):
    user_id: int
    role: RoleEnum

class EventPermissionCreate(EventPermissionBase):
    pass

class EventPermissionUpdate(BaseModel):
    role: RoleEnum # Only role can be updated

# This schema represents an EventPermission ORM model
class EventPermissionInDB(EventPermissionBase):
    id: int
    event_id: int # Added this, as it's part of the model and useful
    granted_at: datetime.datetime
    model_config = {"from_attributes": True}

# This is the main schema for API responses regarding a permission
class EventPermission(EventPermissionInDB):
    # user_id and role are inherited from EventPermissionInDB (via EventPermissionBase)
    user: Optional['UserPublic'] = None # Populate this with user details using forward reference

# For POST /api/events/{id}/share request body
class ShareEventUserPermission(BaseModel):
    user_id: int = Field(..., description="ID of the user to share with")
    role: RoleEnum = Field(..., description="Role to grant to the user for the event")

class ShareEventRequest(BaseModel):
    users: List[ShareEventUserPermission] = Field(..., min_length=1, description="List of users and their roles to share the event with")