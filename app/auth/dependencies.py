"""FastAPI dependencies for authentication and authorization."""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth.models import User, Subscription, SubscriptionPlan, SubscriptionStatus
from app.auth.service import AuthService
from app.storage.db import make_session, get_engine


# Database setup - matches ingest.py pattern
def _get_db_session():
    """Create a new database session."""
    from pathlib import Path
    from app.storage.db import resolve_database_file
    
    BASE_PATH = Path(__file__).resolve().parent.parent
    FALLBACK_DATABASE_FILE = (BASE_PATH.parent / "orwa_lowes.sqlite").resolve()
    DATABASE_FILE = resolve_database_file(fallback=FALLBACK_DATABASE_FILE)
    
    engine = get_engine(str(DATABASE_FILE), busy_timeout=30.0)
    session_factory = make_session(engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def get_session() -> Session:
    """Dependency to get a database session."""
    return next(_get_db_session())


async def get_optional_user(request: Request) -> User | None:
    """
    Get the current user from session if logged in.
    Returns None if not authenticated.
    """
    session_data = getattr(request.scope.get("session"), "__iter__", lambda: iter({}))
    if not hasattr(request, "scope") or "session" not in request.scope:
        return None
    
    session = request.scope.get("session", {})
    user_id = session.get("user_id")
    
    if not user_id:
        return None
    
    # Get database session
    db_session = None
    try:
        db_session = next(_get_db_session())
        auth_service = AuthService(db_session)
        user = auth_service.get_user_by_id(user_id)
        return user
    except Exception:
        return None
    finally:
        if db_session:
            db_session.close()


async def get_current_user(request: Request) -> User:
    """
    Get the current authenticated user.
    Raises HTTPException 401 if not logged in.
    """
    user = await get_optional_user(request)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )
    
    return user


async def require_subscription(
    request: Request,
    min_plan: SubscriptionPlan = SubscriptionPlan.PRO,
) -> User:
    """
    Require an active subscription at the specified tier or higher.
    """
    user = await get_current_user(request)
    
    # Plan hierarchy
    plan_levels = {
        SubscriptionPlan.FREE: 0,
        SubscriptionPlan.BASIC: 1,
        SubscriptionPlan.PRO: 2,
        SubscriptionPlan.ENTERPRISE: 3,
    }
    
    db_session = None
    try:
        db_session = next(_get_db_session())
        auth_service = AuthService(db_session)
        subscription = auth_service.get_subscription(user.id)
        
        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Subscription required",
            )
        
        if not subscription.is_active_subscription():
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Your subscription is not active",
            )
        
        user_level = plan_levels.get(subscription.plan, 0)
        required_level = plan_levels.get(min_plan, 1)
        
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"This feature requires a {min_plan.value} subscription or higher",
            )
        
        return user
    finally:
        if db_session:
            db_session.close()


def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Require the user to be an admin."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user


# Convenience type aliases for dependency injection
CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]
AdminUser = Annotated[User, Depends(require_admin)]
