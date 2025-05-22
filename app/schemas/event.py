# app/schemas/event.py
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any # Ensure Union is imported if you use it for BatchEventCreateResponse
import datetime
# from app.db.models import RoleEnum # Not directly used in this file, but good if it were

# Forward reference for EventPermission to be used in EventWithCurrentVersion
# We'll resolve this with model_rebuild() in __init__.py
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .permission import EventPermission # For type hinting only

# --- Event Recurrence ---
class EventRecurrence(BaseModel):
    is_recurring: bool = False
    recurrence_pattern: Optional[str] = None

    @field_validator('recurrence_pattern')
    @classmethod
    def validate_recurrence_pattern(cls, v: Optional[str], values):
        is_recurring = values.data.get('is_recurring', False)
        if is_recurring and not v:
            raise ValueError("recurrence_pattern is required if is_recurring is True")
        if not is_recurring and v is not None: # If not recurring, pattern should be None
            raise ValueError("recurrence_pattern must be null if is_recurring is False")
        # TODO: Add actual rrule string validation (e.g., using python-dateutil parse)
        return v

# --- Event Version ---
class EventVersionBase(EventRecurrence):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    start_time: datetime.datetime
    end_time: datetime.datetime
    location: Optional[str] = Field(None, max_length=255)

    @field_validator('end_time')
    @classmethod
    def validate_end_time_after_start_time(cls, v: datetime.datetime, values):
        start_time = values.data.get('start_time')
        if start_time and v <= start_time:
            raise ValueError("end_time must be after start_time")
        return v

class EventVersionCreate(EventVersionBase):
    pass

class EventVersion(EventVersionBase):
    id: int
    event_id: int
    version_number: int
    changed_at: datetime.datetime
    changed_by_user_id: int

    model_config = {"from_attributes": True} # Pydantic v2 config

# --- Event (Core/Metadata) ---
class EventBase(BaseModel):
    pass

class EventCreate(EventVersionBase): # Data for the first version of the event
    pass

class EventInDBBase(EventBase):
    id: int
    owner_id: int
    current_version_id: Optional[int] = None
    created_at: datetime.datetime
    model_config = {"from_attributes": True}

class Event(EventInDBBase): # Represents an Event ORM model with its current_version_data
    current_version_data: Optional[EventVersion] = None # Populated if current_version relation is loaded

# More practical response for GET /events/{id}
class EventWithCurrentVersion(BaseModel):
    id: int
    owner_id: int
    created_at: datetime.datetime
    title: str
    description: Optional[str]
    start_time: datetime.datetime
    end_time: datetime.datetime
    location: Optional[str]
    is_recurring: bool
    recurrence_pattern: Optional[str]
    version_id: int
    version_number: int
    last_changed_at: datetime.datetime
    last_changed_by_user_id: int
    permissions: Optional[List['EventPermission']] = [] # Use forward reference string

    model_config = {"from_attributes": True}

# Schema for updating an event (creates a new version)
class EventUpdate(BaseModel): # All fields are optional for PATCH-like behavior
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    start_time: Optional[datetime.datetime] = None
    end_time: Optional[datetime.datetime] = None
    location: Optional[str] = Field(None, max_length=255)
    is_recurring: Optional[bool] = None
    recurrence_pattern: Optional[str] = None # Can be None to remove recurrence

    # Validator for recurrence_pattern during update
    @field_validator('recurrence_pattern')
    @classmethod
    def validate_recurrence_pattern_update(cls, v: Optional[str], values):
        is_recurring = values.data.get('is_recurring')
        # If is_recurring is explicitly being set to True, pattern is required
        if is_recurring is True and not v:
            raise ValueError("recurrence_pattern is required if is_recurring is set to True")
        # If is_recurring is explicitly being set to False, pattern must be None
        if is_recurring is False and v is not None:
            raise ValueError("recurrence_pattern must be null if is_recurring is set to False")
        # If is_recurring is not in payload, and pattern is provided, that's complex.
        # For now, this covers explicit changes. Service layer might need more logic.
        return v

    # Validator for end_time during update
    @field_validator('end_time')
    @classmethod
    def validate_end_time_after_start_time_update(cls, v: Optional[datetime.datetime], values):
        # This validator needs access to potentially unchanged start_time from DB for full validation.
        # Pydantic validators here can only validate based on data *provided in the update payload*.
        # If only end_time is provided, start_time here will be None.
        # The service layer will need to handle cross-validation with existing DB state.
        start_time_in_payload = values.data.get('start_time')
        if start_time_in_payload and v and v <= start_time_in_payload:
            raise ValueError("end_time must be after start_time when both are provided in update")
        return v

# For representing an actual occurrence of a (possibly recurring) event for GET /events list
class EventInstance(BaseModel):
    event_id: int # ID of the original Event record
    title: str
    instance_start_time: datetime.datetime # The specific start time of this occurrence
    instance_end_time: datetime.datetime   # The specific end time of this occurrence
    location: Optional[str] = None
    # You might add original_event_description, etc., if needed for the list view.
    model_config = {"from_attributes": True} # if populated from an object

# For batch event creation
class BatchEventCreateRequestItem(EventCreate): # Each item is like a single event creation
    pass

class BatchEventCreateRequest(BaseModel):
    events: List[BatchEventCreateRequestItem] = Field(..., min_length=1)

# For batch response, using EventWithCurrentVersion for each successfully created event
class BatchEventCreateResponse(BaseModel):
    results: List[EventWithCurrentVersion]
    # Consider adding a field for errors if you want to report partial failures:
    # errors: List[Dict[str, Any]] = []

# For Changelog (GET /events/{id}/history/{versionId} might use EventVersion)
# GET /events/{id}/changelog might use this:
class EventChangeLogEntry(BaseModel):
    version_id: int
    version_number: int
    changed_at: datetime.datetime
    changed_by_user_id: int
    # changed_by_username: Optional[str] = None # Could be populated by service layer
    # description_of_change: Optional[str] = None # If you store diff summaries
    model_config = {"from_attributes": True}

# For Diff (GET /events/{id}/diff/{v1}/{v2})
class EventDiff(BaseModel):
    # Example: { "field_name": { "old_value": "X", "new_value": "Y" } }
    # The actual structure will depend on your diffing library (e.g., deepdiff output)
    differences: Dict[str, Any]

# --- DELETED DUPLICATE DEFINITIONS from here ---