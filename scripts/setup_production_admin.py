#!/usr/bin/env python
"""
One-time admin setup for production deployment.
Creates admin tables and admin user for 93robingattis@gmail.com
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.storage.db import get_engine, make_session, resolve_database_file
from app.auth.models import Base as AuthBase, User, Subscription, SubscriptionStatus
from app.admin.models import Base as AdminBase
from sqlalchemy import text
import sqlite3


def setup_admin():
    DATABASE_PATH = "/var/data/clean_db_v3.sqlite"

    print("=" * 60)
    print("🔧 PRODUCTION ADMIN SETUP")
    print("=" * 60)
    print(f"Database: {DATABASE_PATH}")

    engine = get_engine(DATABASE_PATH)
    session_factory = make_session(engine)
    session = session_factory()

    try:
        print("\n📊 Creating admin tables...")
        AdminBase.metadata.create_all(engine)
        print("✅ Admin tables created")

        print("\n👤 Setting up admin user...")
        existing_admin = (
            session.query(User).filter(User.email == "93robingattis@gmail.com").first()
        )

        if existing_admin:
            print(f"ℹ️  User already exists, updating admin privileges...")
            existing_admin.is_admin = True
            existing_admin.is_active = True
            user = existing_admin
        else:
            print(f"ℹ️  Creating new admin user...")
            user = User(
                email="93robingattis@gmail.com",
                hashed_password="$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5GyYKwq5qDx1",  # Alphonse5150$
                is_admin=True,
                is_active=True,
            )
            session.add(user)
            session.flush()

        existing_sub = (
            session.query(Subscription).filter(Subscription.user_id == user.id).first()
        )
        if not existing_sub:
            print(f"ℹ️  Creating PRO subscription...")
            sub = Subscription(
                user_id=user.id,
                plan_value="pro",
                status_value=SubscriptionStatus.ACTIVE.value,
            )
            session.add(sub)

        session.commit()

        print("=" * 60)
        print("✅ ADMIN SETUP COMPLETE")
        print("=" * 60)
        print(f"Email: {user.email}")
        print(f"Password: Alphonse5150$")
        print(f"Is Admin: {user.is_admin}")
        print("=" * 60)
        print("\nAdmin delete endpoints available:")
        print("DELETE /admin/api/deal/{deal_id}")
        print("DELETE /admin/api/deal/sku/{sku}")
        print("=" * 60)

        return True

    except Exception as e:
        session.rollback()
        print(f"❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        session.close()


if __name__ == "__main__":
    success = setup_admin()
    sys.exit(0 if success else 1)
