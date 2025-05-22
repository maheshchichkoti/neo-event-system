# app/schemas/__init__.py
from .token import Token, TokenData, RefreshToken, TokenPair
from .user import User, UserCreate, UserInDBBase, UserPublic # CORRECT
from .event import (
    EventBase,
    EventCreate,
    EventUpdate,
    EventInDBBase,
    Event,
    EventWithCurrentVersion,
    EventVersionBase,
    EventVersion,
    EventVersionCreate,
    EventRecurrence,
    EventInstance, # Assuming this is the first definition from event.py
    BatchEventCreateRequest, # Assuming this is the first definition
    BatchEventCreateResponse, # Assuming this is the first definition
    EventChangeLogEntry,
    EventDiff
)
from .permission import (
    EventPermissionBase,
    EventPermissionCreate,
    EventPermissionUpdate,
    EventPermission, # This is the main response schema for a permission
    ShareEventRequest,
    ShareEventUserPermission
)

# Update forward references
# Ensure the classes are imported before model_rebuild is called on them.
# The imports above should cover this.

EventWithCurrentVersion.model_rebuild()
EventPermission.model_rebuild() 
User.model_rebuild() 
UserPublic.model_rebuild()
# Add any other models that use string forward references if needed
# e.g., if EventPermission references UserPublic as a string, it needs rebuilding.
# Your EventPermission schema might look like:
# class EventPermission(EventPermissionBase):
#     user: Optional['UserPublic'] = None # <-- This is a forward reference string
# So EventPermission.model_rebuild() is important.