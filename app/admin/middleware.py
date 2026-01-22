"""Middleware for tracking user activity."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.admin.service import AdminService
from app.storage.db import get_engine, make_session, resolve_database_file
from pathlib import Path


class UserActivityMiddleware(BaseHTTPMiddleware):
    """Middleware to track user activity and maintain active sessions."""

    def __init__(self, app, database_file: str):
        super().__init__(app)
        self.database_file = database_file
        # Create engine and session factory
        engine = get_engine(database_file)
        self.session_factory = make_session(engine)

    def _get_client_ip(self, request: Request) -> str | None:
        """Extract client IP from request headers."""
        # Check X-Forwarded-For (behind proxy/load balancer)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # Take the first IP in the chain
            return forwarded.split(",")[0].strip()

        # Check X-Real-IP
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        # Fallback to direct client
        if request.client:
            return request.client.host

        return None

    def _get_user_agent(self, request: Request) -> str | None:
        """Extract user agent from request headers."""
        return request.headers.get("User-Agent")

    def _generate_session_token(self, user_id: int, ip: str | None, timestamp: str) -> str:
        """Generate a unique session token."""
        data = f"{user_id}:{ip or 'unknown'}:{timestamp}"
        return hashlib.sha256(data.encode()).hexdigest()

    async def dispatch(self, request: Request, call_next):
        """Process request and track user activity."""
        # Get user from session
        session = request.scope.get("session", {})
        user_id = session.get("user_id")

        # Execute the request
        response: Response = await call_next(request)

        # Track activity if user is logged in
        if user_id:
            ip_address = self._get_client_ip(request)
            user_agent = self._get_user_agent(request)

            # Determine activity type based on the request
            activity_type = "page_view"
            path = request.url.path

            if path.startswith("/auth/login") and request.method == "POST":
                activity_type = "login"
            elif path.startswith("/auth/logout"):
                activity_type = "logout"
            elif path.startswith("/api/"):
                activity_type = "api_call"

            # Log activity in background (don't block the response)
            try:
                with self.session_factory() as db_session:
                    admin_service = AdminService(db_session)

                    # Log the activity
                    admin_service.log_activity(
                        user_id=user_id,
                        activity_type=activity_type,
                        ip_address=ip_address,
                        user_agent=user_agent,
                    )

                    # Update or create active session
                    session_token = session.get("session_token")
                    if not session_token:
                        # Generate new session token
                        session_token = self._generate_session_token(
                            user_id,
                            ip_address,
                            datetime.now(timezone.utc).isoformat()
                        )
                        session["session_token"] = session_token

                    admin_service.create_or_update_session(
                        user_id=user_id,
                        session_token=session_token,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        expires_in_hours=24,
                    )

                    # Handle logout - delete session
                    if activity_type == "logout":
                        admin_service.delete_session(session_token)

            except Exception as e:
                # Don't let activity tracking errors break the app
                import logging
                logging.getLogger(__name__).warning(
                    "Failed to track user activity: %s", e
                )

        return response
