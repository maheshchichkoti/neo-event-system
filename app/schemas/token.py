# app/schemas/token.py
from pydantic import BaseModel
from typing import Optional

class Token(BaseModel):
    access_token: str
    token_type: str

class RefreshToken(BaseModel):
    refresh_token: str

class TokenPair(Token, RefreshToken): # Inherits from both
    pass

class TokenData(BaseModel):
    username: Optional[str] = None
    user_id: Optional[int] = None # Added user_id for easier lookup
    # You can add more claims here if needed, like roles or permissions