"""
One-time script to create admin account on production.
Run this via Render shell or as a one-time endpoint.
"""

from app.storage.db import get_engine, make_session, resolve_database_file
from app.auth.models import User, Subscription, SubscriptionPlan, SubscriptionStatus
from app.auth.service import AuthService
from datetime import datetime, timezone, timedelta
from pathlib import Path

def create_admin_account():
    """Create admin account with PRO subscription."""

    # Use production database path
    BASE_PATH = Path(__file__).resolve().parent.parent
    FALLBACK_DATABASE_FILE = (BASE_PATH / "orwa_lowes.sqlite").resolve()
    DATABASE_FILE = resolve_database_file(fallback=FALLBACK_DATABASE_FILE)

    engine = get_engine(str(DATABASE_FILE))
    session_factory = make_session(engine)
    session = session_factory()

    try:
        auth_service = AuthService(session)

        # Check if user exists
        existing_user = session.query(User).filter(User.email == '93robingattis@gmail.com').first()

        if existing_user:
            print(f'User already exists with ID: {existing_user.id}')
            user = existing_user
        else:
            # Create user
            user = auth_service.register_user(
                email='93robingattis@gmail.com',
                password='Alphonse5150$',
                display_name='Robin Gattis'
            )
            print(f'Created new user with ID: {user.id}')

        # Check if subscription exists
        existing_sub = session.query(Subscription).filter(Subscription.user_id == user.id).first()

        if existing_sub:
            # Update to PRO
            existing_sub.plan = SubscriptionPlan.PRO
            existing_sub.status = SubscriptionStatus.ACTIVE
            existing_sub.current_period_end = datetime.now(timezone.utc) + timedelta(days=365)
            print('Updated existing subscription to PRO')
        else:
            # Create PRO subscription (shouldn't happen as register_user creates FREE sub)
            subscription = Subscription(
                user_id=user.id,
                plan=SubscriptionPlan.PRO,
                status=SubscriptionStatus.ACTIVE,
                stripe_customer_id='admin_manual',
                stripe_subscription_id='admin_manual',
                current_period_start=datetime.now(timezone.utc),
                current_period_end=datetime.now(timezone.utc) + timedelta(days=365),
                created_at=datetime.now(timezone.utc),
            )
            session.add(subscription)
            print('Created PRO subscription')

        session.commit()
        print('✅ SUCCESS: Admin account ready!')
        print('Email: 93robingattis@gmail.com')
        print('Password: Alphonse5150$')
        print('Plan: PRO (active for 365 days)')
        return True

    except Exception as e:
        session.rollback()
        print(f'❌ ERROR: {e}')
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()

if __name__ == "__main__":
    create_admin_account()
