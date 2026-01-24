"""Service layer for admin functionality."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, desc, and_, select, delete
from sqlalchemy.orm import Session

from app.admin.models import (
    ScraperHeartbeat,
    SystemMessage,
    UserActivity,
    ActiveSession,
    IngestionMetrics,
)
from app.auth.models import User, Subscription, PaymentHistory
from app.storage.models_sql import StorePriceHistory, Observation, Store


class AdminService:
    """Service for admin operations."""

    def __init__(self, session: Session):
        self.session = session

    # ──────────────────────────────────────────────────────────────────────────
    # Scraper Heartbeat Management
    # ──────────────────────────────────────────────────────────────────────────

    def update_heartbeat(
        self,
        scraper_id: str,
        scraper_name: str | None = None,
        deals_count: int = 0,
        errors_count: int = 0,
        status_message: str | None = None,
        version: str | None = None,
        hostname: str | None = None,
    ) -> ScraperHeartbeat:
        """Update or create scraper heartbeat record."""
        heartbeat = (
            self.session.query(ScraperHeartbeat)
            .filter_by(scraper_id=scraper_id)
            .first()
        )

        now = datetime.now(timezone.utc)

        if heartbeat is None:
            heartbeat = ScraperHeartbeat(
                scraper_id=scraper_id,
                scraper_name=scraper_name or scraper_id,
                last_heartbeat=now,
                first_seen=now,
                is_active=True,
                deals_ingested_total=deals_count,
                deals_ingested_session=deals_count,
                errors_count=errors_count,
                version=version,
                hostname=hostname,
                status_message=status_message,
            )
            self.session.add(heartbeat)
        else:
            heartbeat.last_heartbeat = now
            heartbeat.is_active = True
            heartbeat.deals_ingested_total += deals_count
            heartbeat.deals_ingested_session += deals_count
            heartbeat.errors_count += errors_count
            if scraper_name:
                heartbeat.scraper_name = scraper_name
            if status_message:
                heartbeat.status_message = status_message
            if version:
                heartbeat.version = version
            if hostname:
                heartbeat.hostname = hostname

        self.session.commit()
        return heartbeat

    def get_active_scrapers(self, timeout_minutes: int = 5) -> list[ScraperHeartbeat]:
        """Get all scrapers that have sent a heartbeat within the timeout window."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
        return (
            self.session.query(ScraperHeartbeat)
            .filter(ScraperHeartbeat.last_heartbeat >= cutoff)
            .filter(ScraperHeartbeat.is_active == True)
            .order_by(desc(ScraperHeartbeat.last_heartbeat))
            .all()
        )

    def get_all_scrapers(self) -> list[ScraperHeartbeat]:
        """Get all scraper heartbeat records, ordered by last heartbeat."""
        return (
            self.session.query(ScraperHeartbeat)
            .order_by(desc(ScraperHeartbeat.last_heartbeat))
            .all()
        )

    def mark_scraper_inactive(self, scraper_id: str) -> bool:
        """Mark a scraper as inactive."""
        heartbeat = (
            self.session.query(ScraperHeartbeat)
            .filter_by(scraper_id=scraper_id)
            .first()
        )
        if heartbeat:
            heartbeat.is_active = False
            heartbeat.status_message = "Manually deactivated"
            self.session.commit()
            return True
        return False

    # ──────────────────────────────────────────────────────────────────────────
    # System Messages
    # ──────────────────────────────────────────────────────────────────────────

    def create_system_message(
        self,
        message: str,
        message_type: str = "info",
        priority: int = 0,
        created_by_user_id: int | None = None,
        expires_at: datetime | None = None,
    ) -> SystemMessage:
        """Create a new system message."""
        msg = SystemMessage(
            message=message,
            message_type=message_type,
            priority=priority,
            created_by_user_id=created_by_user_id,
            expires_at=expires_at,
            is_active=True,
        )
        self.session.add(msg)
        self.session.commit()
        return msg

    def get_active_system_messages(self) -> list[SystemMessage]:
        """Get all active system messages, ordered by priority."""
        now = datetime.now(timezone.utc)
        return (
            self.session.query(SystemMessage)
            .filter(SystemMessage.is_active == True)
            .filter(
                (SystemMessage.expires_at == None) | (SystemMessage.expires_at > now)
            )
            .order_by(desc(SystemMessage.priority), desc(SystemMessage.created_at))
            .all()
        )

    def update_system_message(
        self,
        message_id: int,
        message: str | None = None,
        message_type: str | None = None,
        priority: int | None = None,
        is_active: bool | None = None,
        expires_at: datetime | None = None,
    ) -> SystemMessage | None:
        """Update an existing system message."""
        msg = self.session.get(SystemMessage, message_id)
        if msg:
            if message is not None:
                msg.message = message
            if message_type is not None:
                msg.message_type = message_type
            if priority is not None:
                msg.priority = priority
            if is_active is not None:
                msg.is_active = is_active
            if expires_at is not None:
                msg.expires_at = expires_at
            self.session.commit()
        return msg

    def delete_system_message(self, message_id: int) -> bool:
        """Delete a system message."""
        msg = self.session.get(SystemMessage, message_id)
        if msg:
            self.session.delete(msg)
            self.session.commit()
            return True
        return False

    # ──────────────────────────────────────────────────────────────────────────
    # User Activity Tracking
    # ──────────────────────────────────────────────────────────────────────────

    def log_activity(
        self,
        user_id: int,
        activity_type: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        extra_data: str | None = None,
    ) -> UserActivity:
        """Log a user activity event."""
        activity = UserActivity(
            user_id=user_id,
            activity_type=activity_type,
            ip_address=ip_address,
            user_agent=user_agent,
            extra_data=extra_data,
        )
        self.session.add(activity)
        self.session.commit()
        return activity

    def get_user_activities(
        self,
        user_id: int,
        limit: int = 100,
        activity_type: str | None = None,
    ) -> list[UserActivity]:
        """Get recent activities for a user."""
        query = self.session.query(UserActivity).filter(UserActivity.user_id == user_id)
        if activity_type:
            query = query.filter(UserActivity.activity_type == activity_type)
        return query.order_by(desc(UserActivity.occurred_at)).limit(limit).all()

    def get_unique_ips_for_user(self, user_id: int) -> list[str]:
        """Get all unique IP addresses a user has logged in from."""
        result = (
            self.session.query(UserActivity.ip_address)
            .filter(UserActivity.user_id == user_id)
            .filter(UserActivity.ip_address != None)
            .distinct()
            .all()
        )
        return [ip[0] for ip in result if ip[0]]

    def get_last_login(self, user_id: int) -> UserActivity | None:
        """Get the most recent login activity for a user."""
        return (
            self.session.query(UserActivity)
            .filter(UserActivity.user_id == user_id)
            .filter(UserActivity.activity_type == "login")
            .order_by(desc(UserActivity.occurred_at))
            .first()
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Active Sessions
    # ──────────────────────────────────────────────────────────────────────────

    def create_or_update_session(
        self,
        user_id: int,
        session_token: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        expires_in_hours: int = 24,
    ) -> ActiveSession:
        """Create or update an active session."""
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=expires_in_hours)

        session = (
            self.session.query(ActiveSession)
            .filter_by(session_token=session_token)
            .first()
        )

        if session:
            session.last_activity = now
            session.expires_at = expires_at
        else:
            session = ActiveSession(
                user_id=user_id,
                session_token=session_token,
                ip_address=ip_address,
                user_agent=user_agent,
                created_at=now,
                last_activity=now,
                expires_at=expires_at,
            )
            self.session.add(session)

        self.session.commit()
        return session

    def delete_session(self, session_token: str) -> bool:
        """Delete an active session."""
        session = (
            self.session.query(ActiveSession)
            .filter_by(session_token=session_token)
            .first()
        )
        if session:
            self.session.delete(session)
            self.session.commit()
            return True
        return False

    def get_active_sessions_for_user(self, user_id: int) -> list[ActiveSession]:
        """Get all active sessions for a user."""
        now = datetime.now(timezone.utc)
        return (
            self.session.query(ActiveSession)
            .filter(ActiveSession.user_id == user_id)
            .filter(
                (ActiveSession.expires_at == None) | (ActiveSession.expires_at > now)
            )
            .order_by(desc(ActiveSession.last_activity))
            .all()
        )

    def cleanup_expired_sessions(self) -> int:
        """Remove expired sessions from the database."""
        now = datetime.now(timezone.utc)
        result = self.session.execute(
            delete(ActiveSession).where(
                and_(ActiveSession.expires_at != None, ActiveSession.expires_at < now)
            )
        )
        self.session.commit()
        return result.rowcount

    # ──────────────────────────────────────────────────────────────────────────
    # User Management
    # ──────────────────────────────────────────────────────────────────────────

    def get_all_users_with_stats(self) -> list[dict[str, Any]]:
        """Get all users with subscription and activity stats."""
        users = self.session.query(User).all()
        result = []

        for user in users:
            # Get subscription
            subscription = (
                self.session.query(Subscription).filter_by(user_id=user.id).first()
            )

            # Get total spent
            total_spent = (
                self.session.query(func.sum(PaymentHistory.amount))
                .filter(PaymentHistory.user_id == user.id)
                .filter(PaymentHistory.status == "succeeded")
                .scalar()
                or 0.0
            )

            # Get last activity
            last_activity = (
                self.session.query(UserActivity)
                .filter(UserActivity.user_id == user.id)
                .order_by(desc(UserActivity.occurred_at))
                .first()
            )

            # Check if currently logged in
            active_sessions = self.get_active_sessions_for_user(user.id)
            is_online = len(active_sessions) > 0

            # Get unique IPs
            unique_ips = self.get_unique_ips_for_user(user.id)

            result.append(
                {
                    "user": user,
                    "subscription": subscription,
                    "total_spent": total_spent,
                    "last_activity": last_activity.occurred_at
                    if last_activity
                    else None,
                    "is_online": is_online,
                    "active_sessions_count": len(active_sessions),
                    "unique_ips_count": len(unique_ips),
                    "unique_ips": unique_ips[:5],  # First 5 IPs for display
                }
            )

        # Sort: online users first, then by last activity
        result.sort(
            key=lambda x: (
                not x["is_online"],
                x["last_activity"] or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )
        return result

    # ──────────────────────────────────────────────────────────────────────────
    # Deal Management
    # ──────────────────────────────────────────────────────────────────────────

    def get_recent_deals(
        self,
        *,
        limit: int = 200,
        q: str | None = None,
        clearance_only: bool = True,
    ) -> list[StorePriceHistory]:
        query = self.session.query(StorePriceHistory)
        if clearance_only:
            query = query.filter(StorePriceHistory.clearance == True)

        q_text = (q or "").strip()
        if q_text:
            # If you paste a SKU, this finds it. Otherwise it does a loose title match.
            if q_text.isdigit():
                query = query.filter(StorePriceHistory.sku == q_text)
            else:
                query = query.filter(StorePriceHistory.title.ilike(f"%{q_text}%"))

        return (
            query.order_by(
                desc(StorePriceHistory.updated_at), desc(StorePriceHistory.id)
            )
            .limit(limit)
            .all()
        )

    def delete_deal_by_id(self, deal_id: int) -> bool:
        """Delete a deal (and its bounded history) from store price history."""
        deal = self.session.get(StorePriceHistory, deal_id)
        if not deal:
            return False

        result = self.session.execute(
            delete(StorePriceHistory).where(
                and_(
                    StorePriceHistory.retailer == deal.retailer,
                    StorePriceHistory.store_id == deal.store_id,
                    StorePriceHistory.sku == deal.sku,
                )
            )
        )
        self.session.commit()
        return (result.rowcount or 0) > 0

    def delete_deals_by_sku(self, sku: str) -> int:
        """Delete all deals for a specific SKU."""
        result = self.session.execute(
            delete(StorePriceHistory).where(StorePriceHistory.sku == sku)
        )
        self.session.commit()
        return result.rowcount

    # ──────────────────────────────────────────────────────────────────────────
    # Store Statistics
    # ──────────────────────────────────────────────────────────────────────────

    def get_store_discount_averages(self, hours: int = 24) -> list[dict[str, Any]]:
        """Calculate average discount percentage per store for recent deals."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Join with Store table to get actual store names
        result = (
            self.session.query(
                StorePriceHistory.store_id,
                Store.name.label("store_name"),
                Store.city.label("store_city"),
                Store.state.label("store_state"),
                func.avg(StorePriceHistory.pct_off).label("avg_discount"),
                func.count(StorePriceHistory.id).label("deal_count"),
                func.max(StorePriceHistory.updated_at).label("last_updated"),
            )
            .outerjoin(Store, StorePriceHistory.store_id == Store.id)
            .filter(StorePriceHistory.clearance == True)
            .filter(StorePriceHistory.updated_at >= cutoff)
            .filter(StorePriceHistory.pct_off != None)
            .group_by(StorePriceHistory.store_id, Store.name, Store.city, Store.state)
            .order_by(desc("avg_discount"))
            .all()
        )

        return [
            {
                "store_id": row.store_id,
                "store_name": f"{row.store_city}, {row.store_state} (#{row.store_id})"
                if row.store_city and row.store_state
                else (row.store_name or f"Store #{row.store_id}"),
                "avg_discount": round(row.avg_discount or 0, 2),
                "deal_count": row.deal_count,
                "last_updated": row.last_updated,
            }
            for row in result
        ]

    # ──────────────────────────────────────────────────────────────────────────
    # Ingestion Metrics
    # ──────────────────────────────────────────────────────────────────────────

    def get_ingestion_rate(self, hours: int = 1) -> dict[str, Any]:
        """Calculate current ingestion rate based on recent price history updates."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        # Count deals in the time window (use StorePriceHistory since that's what ingest API writes to)
        deal_count = (
            self.session.query(func.count(StorePriceHistory.id))
            .filter(StorePriceHistory.updated_at >= cutoff)
            .scalar()
            or 0
        )

        # Get unique stores
        unique_stores = (
            self.session.query(func.count(func.distinct(StorePriceHistory.store_id)))
            .filter(StorePriceHistory.updated_at >= cutoff)
            .scalar()
            or 0
        )

        # Get unique SKUs
        unique_skus = (
            self.session.query(func.count(func.distinct(StorePriceHistory.sku)))
            .filter(StorePriceHistory.updated_at >= cutoff)
            .scalar()
            or 0
        )

        # Calculate rate per minute
        minutes = hours * 60
        rate_per_minute = deal_count / minutes if minutes > 0 else 0

        return {
            "time_window_hours": hours,
            "total_deals": deal_count,
            "unique_stores": unique_stores,
            "unique_skus": unique_skus,
            "deals_per_minute": round(rate_per_minute, 2),
            "deals_per_hour": round(rate_per_minute * 60, 2),
        }

    def get_dashboard_metrics(self) -> dict[str, Any]:
        """Get comprehensive dashboard metrics for admin panel."""
        # Scraper status
        active_scrapers = self.get_active_scrapers(timeout_minutes=5)
        all_scrapers = self.get_all_scrapers()

        # Ingestion rate
        ingestion_1h = self.get_ingestion_rate(hours=1)
        ingestion_24h = self.get_ingestion_rate(hours=24)

        # Store stats
        store_averages = self.get_store_discount_averages(hours=24)

        # User stats
        total_users = self.session.query(func.count(User.id)).scalar() or 0
        users_online = (
            self.session.query(func.count(func.distinct(ActiveSession.user_id)))
            .filter(ActiveSession.expires_at > datetime.now(timezone.utc))
            .scalar()
            or 0
        )

        # Subscription breakdown
        subscription_counts = (
            self.session.query(Subscription.plan, func.count(Subscription.id))
            .group_by(Subscription.plan)
            .all()
        )

        return {
            "scrapers": {
                "active_count": len(active_scrapers),
                "total_count": len(all_scrapers),
                "scrapers": [
                    {
                        "id": s.scraper_id,
                        "name": s.scraper_name,
                        "last_heartbeat": s.last_heartbeat,
                        "deals_total": s.deals_ingested_total,
                        "deals_session": s.deals_ingested_session,
                        "errors": s.errors_count,
                        "version": s.version,
                    }
                    for s in active_scrapers
                ],
            },
            "ingestion": {
                "last_hour": ingestion_1h,
                "last_24_hours": ingestion_24h,
            },
            "stores": {
                "top_discounts": store_averages[:10],  # Top 10 stores
            },
            "users": {
                "total": total_users,
                "online": users_online,
                "subscriptions": {
                    plan.value: count for plan, count in subscription_counts
                },
            },
        }
