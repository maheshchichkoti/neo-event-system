import enum
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, ForeignKey, Enum as SQLAlchemyEnum, UniqueConstraint, Text
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base # Make sure this points to your declarative_base()

# --- Enums ---
class RoleEnum(str, enum.Enum): # Inheriting from str makes it directly usable as string values
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"

# --- Models ---
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False) # Max length for emails
    hashed_password = Column(String(255), nullable=False) # Store hashed passwords
    is_active = Column(Boolean, default=True)
    # is_superuser = Column(Boolean, default=False) # Optional admin flag

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Relationships
    # Events directly owned by the user
    owned_events = relationship("Event", back_populates="owner", foreign_keys="Event.owner_id")
    
    # Permissions granted to this user for various events
    permissions = relationship("EventPermission", back_populates="user")
    
    # Versions of events changed by this user
    event_versions_changed = relationship("EventVersion", back_populates="changed_by_user", foreign_keys="EventVersion.changed_by_user_id")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False) # Original creator/owner
    
    # Pointer to the current active version of the event's data
    # We use use_alter=True and name for the FK constraint to handle circular dependency with EventVersion
    current_version_id = Column(Integer, ForeignKey("event_versions.id", use_alter=True, name='fk_event_current_version_id'), unique=True, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # No updated_at here, as updates are tracked via new versions

    # Relationships
    owner = relationship("User", back_populates="owned_events", foreign_keys=[owner_id])
    
    # Relationship to the specific EventVersion row that holds the current state
    # post_update=True helps SQLAlchemy manage the circular dependency update order
    current_version = relationship("EventVersion", foreign_keys=[current_version_id], post_update=True, uselist=False) # Ensure this is one-to-one effectively

    # All historical and current versions related to this event
    versions = relationship(
        "EventVersion",
        back_populates="event_parent", # Connects to EventVersion.event_parent
        cascade="all, delete-orphan",
        order_by="EventVersion.version_number.desc()",
        foreign_keys="EventVersion.event_id" # Explicit FK for this relationship
    )
    
    # Permissions associated with this event
    permissions = relationship("EventPermission", back_populates="event", cascade="all, delete-orphan")


class EventVersion(Base):
    __tablename__ = "event_versions"

    id = Column(Integer, primary_key=True, index=True) # This will be referenced by Event.current_version_id
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True) # FK to Event.id
    version_number = Column(Integer, nullable=False) # Sequential per event, starting from 1

    # Snapshot of event data fields at this version
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True) # Text for longer descriptions
    start_time = Column(DateTime(timezone=True), nullable=False, index=True) # For non-recurring, or start of first occurrence
    end_time = Column(DateTime(timezone=True), nullable=False, index=True)   # For non-recurring, or end of first occurrence
    location = Column(String(255), nullable=True)
    is_recurring = Column(Boolean, default=False, nullable=False)
    recurrence_pattern = Column(String(255), nullable=True) # rrule string, e.g., "FREQ=WEEKLY;BYDAY=MO,WE,FR;UNTIL=20231231T000000Z"

    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    changed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False) # User who made this version
    # change_description = Column(String(255), nullable=True) # Optional: brief note about the change

    # Relationships
    event_parent = relationship("Event", back_populates="versions", foreign_keys=[event_id]) # Link back to the main Event entity
    changed_by_user = relationship("User", back_populates="event_versions_changed", foreign_keys=[changed_by_user_id])

    __table_args__ = (
        UniqueConstraint('event_id', 'version_number', name='uq_event_version_number'),
        # Consider indexing other frequently queried fields in EventVersion like start_time, end_time if using them for direct lookups
    )


class EventPermission(Base):
    __tablename__ = "event_permissions"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False) # User who is granted permission
    role = Column(SQLAlchemyEnum(RoleEnum, name="role_enum"), nullable=False) # owner, editor, viewer

    granted_at = Column(DateTime(timezone=True), server_default=func.now())
    # updated_at for role changes? Or just delete and recreate? Simpler to delete/recreate.

    # Relationships
    event = relationship("Event", back_populates="permissions")
    user = relationship("User", back_populates="permissions")

    __table_args__ = (
        UniqueConstraint('event_id', 'user_id', name='uq_event_user_permission'), # A user can only have one role per event
    )