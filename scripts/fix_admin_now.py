"""
Immediately fix the admin account to have PREMIUM access.
Run this script to instantly grant yourself pro access.
"""

import sys
import io
from pathlib import Path

# Fix Unicode output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.storage.db import get_engine, make_session, resolve_database_file
from app.auth.models import User, Subscription, SubscriptionPlan, SubscriptionStatus

# Database setup
BASE_PATH = Path(__file__).resolve().parent.parent
FALLBACK_DATABASE_FILE = (BASE_PATH / "orwa_lowes.sqlite").resolve()
DATABASE_FILE = resolve_database_file(fallback=FALLBACK_DATABASE_FILE)

print(f"Using database: {DATABASE_FILE}")

engine = get_engine(str(DATABASE_FILE))
session_factory = make_session(engine)

target_email = "93robingattis@gmail.com"

with session_factory() as session:
    # Find user
    user = session.query(User).filter(User.email == target_email).first()

    if not user:
        print(f"❌ User {target_email} not found!")
        print("You need to register this account first at /auth/register")
        sys.exit(1)

    print(f"✓ Found user: {user.email} (ID: {user.id})")
    print(f"  Current admin status: {user.is_admin}")

    # Set admin status
    if not user.is_admin:
        user.is_admin = True
        print(f"  → Upgraded to admin")

    # Check subscription
    sub = session.query(Subscription).filter(Subscription.user_id == user.id).first()

    if not sub:
        print(f"  No subscription found - creating PREMIUM subscription")
        sub = Subscription(
            user_id=user.id,
            plan=SubscriptionPlan.PREMIUM,
            status=SubscriptionStatus.ACTIVE,
        )
        session.add(sub)
        print(f"  → Created PREMIUM subscription")
    else:
        print(f"  Current plan: {sub.plan.value}")
        print(f"  Current status: {sub.status.value}")

        if sub.plan != SubscriptionPlan.PREMIUM or sub.status != SubscriptionStatus.ACTIVE:
            sub.plan = SubscriptionPlan.PREMIUM
            sub.status = SubscriptionStatus.ACTIVE
            print(f"  → Updated to PREMIUM/ACTIVE")

    session.commit()

    print(f"\n✅ SUCCESS! {target_email} is now:")
    print(f"   - Admin: {user.is_admin}")
    print(f"   - Plan: {sub.plan.value}")
    print(f"   - Status: {sub.status.value}")
    print(f"   - Active Subscription: {sub.is_active_subscription()}")
    print(f"\n🎉 You now have full PRO access to all deals!")
    print(f"   Log out and log back in to see the changes.")
