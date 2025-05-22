# app/schemas/user.py
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
import datetime

# Shared properties
class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr

# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str = Field(..., min_length=8)

# Properties to receive via API on update (not strictly needed for this challenge's endpoints)
class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=100)
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=8)
    is_active: Optional[bool] = None

# Properties stored in DB
class UserInDBBase(UserBase): # <--- THIS IS THE CLASS NAME
    id: int
    is_active: bool = True
    created_at: datetime.datetime
    updated_at: Optional[datetime.datetime] = None

    class Config:
        from_attributes = True # Pydantic V2 way to enable ORM mode

# Additional properties to return to API (public representation)
class User(UserInDBBase): # User inherits from UserInDBBase
    pass

# For cases where you only want to expose minimal public info (e.g., in shared event lists)
class UserPublic(BaseModel):
    id: int
    username: str

    class Config:
        from_attributes = True