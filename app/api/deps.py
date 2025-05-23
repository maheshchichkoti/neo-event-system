# app/api/deps.py
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import ValidationError

from app.core.config import settings
# from app.core import security # Not directly needed here if ALGORITHM, SECRET_KEY from settings
from app.db.models import User # Your SQLAlchemy User model
from app.schemas.token import TokenData
from app import crud # <--- CORRECT IMPORT FOR CRUD PACKAGE
from app.db.session import get_db
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

async def get_current_user(
    db: AsyncSession = Depends(get_db), token: str = Depends(oauth2_scheme)
) -> User: # Returns SQLAlchemy User model
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        token_type = payload.get("type")
        if token_type != "access":
            raise credentials_exception

        user_id_str: str = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        
        try:
            user_id = int(user_id_str)
        except ValueError:
            raise credentials_exception
        
        # Pydantic validation of the extracted ID (optional but good practice)
        token_data_obj = TokenData(user_id=user_id) # Renamed to avoid confusion with schema module

    except (JWTError, ValidationError): # Catch both JWT and Pydantic validation errors
        raise credentials_exception
        
    # Call the get_user_by_id method on the 'user' instance from the 'crud' package
    user = await crud.user.get_user_by_id(db, user_id=token_data_obj.user_id) # <--- CORRECT CALL
    
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(
    current_user: User = Depends(get_current_user) # User here is SQLAlchemy model
) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user