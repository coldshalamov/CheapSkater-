"""Username update endpoint and model."""

from pydantic import BaseModel
from fastapi import HTTPException
import re


class UpdateUsernameRequest(BaseModel):
    username: str


async def update_username_handler(request, data: UpdateUsernameRequest, get_optional_user, _get_db_session, LOGGER):
    """Update user's username/handle."""
    user = await get_optional_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Validate username
    username = data.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username cannot be empty")
    
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    
    if len(username) > 50:
        raise HTTPException(status_code=400, detail="Username must be 50 characters or less")
    
    # Only allow alphanumeric, underscore, and hyphen
    if not re.match(r'^[a-zA-Z0-9_-]+$', username):
        raise HTTPException(status_code=400, detail="Username can only contain letters, numbers, underscores, and hyphens")
    
    db_session = next(_get_db_session())
    try:
        # Check if username is already taken
        from app.auth.models import User
        existing = db_session.query(User).filter(User.username == username).first()
        if existing and existing.id != user.id:
            raise HTTPException(status_code=400, detail="Username is already taken")
        
        # Update username
        db_user = db_session.query(User).filter(User.id == user.id).first()
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")
        
        db_user.username = username
        db_session.commit()
        
        return {"success": True, "username": username}
    except HTTPException:
        raise
    except Exception as e:
        db_session.rollback()
        LOGGER.error(f"Error updating username: {e}")
        raise HTTPException(status_code=500, detail="Failed to update username")
    finally:
        db_session.close()
