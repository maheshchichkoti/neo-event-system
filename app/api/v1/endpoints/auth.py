# app/api/v1/endpoints/auth.py
from fastapi import APIRouter, Depends, HTTPException, status, Body
from fastapi.security import OAuth2PasswordRequestForm # For standard login form
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas # Use __init__.py for easier imports
from app import crud
from app.db.session import get_db
from app.core.security import verify_password, create_token_pair, decode_token, create_access_token 
from app.api.deps import get_current_active_user # We'll define this dependency soon

router = APIRouter()

@router.post("/register", response_model=schemas.User, status_code=status.HTTP_201_CREATED)
async def register_new_user(
    *,
    db: AsyncSession = Depends(get_db),
    user_in: schemas.UserCreate
):
    """
    Create new user.
    """
    existing_user_by_username = await crud.user.get_user_by_username(db, username=user_in.username)
    if existing_user_by_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this username already exists.",
        )
    existing_user_by_email = await crud.user.get_user_by_email(db, email=user_in.email)
    if existing_user_by_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A user with this email already exists.",
        )
    
    user = await crud.user.create_user(db=db, user_in=user_in)
    return user


@router.post("/login", response_model=schemas.TokenPair)
async def login_for_access_token(
    db: AsyncSession = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends() # Standard form: username, password
):
    """
    OAuth2 compatible token login, get an access token for future requests.
    Username can be the actual username or email.
    """
    user = await crud.user.get_user_by_username(db, username=form_data.username)
    if not user:
        user = await crud.user.get_user_by_email(db, email=form_data.username)

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Inactive user"
        )
    
    # Optionally update last login time
    # await crud.user.update_user_last_login(db, user=user)
    
    # Subject for JWT can be username or user.id. user.id is often preferred.
    token_data = create_token_pair(subject=user.id) # Using user.id as subject
    return token_data


@router.post("/refresh", response_model=schemas.Token)
async def refresh_access_token(
    db: AsyncSession = Depends(get_db),
    refresh_token_data: schemas.RefreshToken = Body(...) # Expecting {"refresh_token": "..."}
):
    """
    Refresh an access token using a valid refresh token.
    """
    token_payload = decode_token(refresh_token_data.refresh_token)
    if not token_payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token: could not decode",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_type = token_payload.get("type")
    if token_type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type: not a refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_id = token_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token: no subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id_int = int(user_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token: subject is not a valid ID",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await crud.user.get_user_by_id(db, user_id=user_id_int)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token: user not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Generate a new access token ONLY
    new_access_token = schemas.Token(
        access_token=create_access_token(subject=user.id),
        token_type="bearer"
    )
    return new_access_token


@router.post("/logout") # No response model needed, or a simple status message
async def logout_user(
    # current_user: models.User = Depends(get_current_active_user) # If you need to know who is logging out
    # For now, let's make it simple: client discards tokens.
    # If server-side denylist is implemented, this endpoint would add token to it.
):
    """
    Logout user. (Client-side token discard)
    If a server-side token denylist was implemented, this endpoint would invalidate the token.
    For this challenge, we'll assume client handles token removal.
    """
    # Here you would add the token to a denylist if you implemented one.
    # For example, if using Redis: redis_client.set(f"denylist_{token_jti}", "logged_out", ex=ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    return {"message": "Logout successful. Please discard your tokens."}

# We will create get_current_active_user dependency in app/api/deps.py next