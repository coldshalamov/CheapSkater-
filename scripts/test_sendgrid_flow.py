#!/usr/bin/env python3
"""
Test script to simulate a complete email alert flow to verify SendGrid integration.

Usage:
    python scripts/test_sendgrid_flow.py

This script will:
1. Create a test user with email rob@redhatfunding.com
2. Create a category-based alert
3. Create test deal data that matches the alert
4. Trigger the notification processor to send an email
5. Display results and check SendGrid integration
"""

import sys
import os
from datetime import datetime, timezone

# Add repo to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.storage.db import get_engine, make_session
from app.auth.models import User, Subscription, SubscriptionPlan, SubscriptionStatus
from app.notifications.models import DealAlert, NotificationType, NotificationFrequency
from app.notifications.processor import process_new_deals
from app.notifications.email_service import is_email_configured
from app.auth.service import hash_password
from app.logging_config import get_logger

LOGGER = get_logger(__name__)

# Get database path from env or use default
DB_PATH = os.getenv("CHEAPSKATER_DB_PATH", "cheapskater.db")

def setup_test_data():
    """Create test user, alert, and deals, then trigger email notification."""

    # Check SendGrid config
    print("\n" + "="*60)
    print("SendGrid Integration Test")
    print("="*60)

    if not is_email_configured():
        print("❌ SendGrid not configured!")
        print("   Set SENDGRID_API_KEY environment variable to enable email.")
        return False

    print("✅ SendGrid is configured")

    # Connect to database
    engine = get_engine(DB_PATH)
    session_factory = make_session(engine)

    try:
        with session_factory() as session:
            # Clean up any existing test user
            existing_user = session.query(User).filter(
                User.email == "rob@redhatfunding.com"
            ).first()

            if existing_user:
                LOGGER.info("Cleaning up existing test user")
                # Delete related records
                session.query(DealAlert).filter(
                    DealAlert.user_id == existing_user.id
                ).delete()
                session.delete(existing_user)
                session.commit()

            # Create test user
            print("\n📝 Creating test user...")
            test_user = User(
                email="rob@redhatfunding.com",
                password_hash=hash_password("testpassword123"),
                display_name="Rob Test",
                is_active=True,
                is_verified=True,
            )
            session.add(test_user)
            session.flush()  # Get the user ID

            # Create subscription
            subscription = Subscription(
                user_id=test_user.id,
                plan=SubscriptionPlan.PRO,
                status=SubscriptionStatus.ACTIVE,
            )
            session.add(subscription)

            print(f"   ✓ User created: {test_user.email}")

            # Create a category-based alert
            print("\n🔔 Creating deal alert...")
            alert = DealAlert(
                user_id=test_user.id,
                name="Power Tools Sale",
                alert_type=NotificationType.CATEGORY,
                category="Power Tools",
                min_discount=0.25,  # 25% off minimum
                email_enabled=True,
                frequency=NotificationFrequency.INSTANT,
                is_active=True,
            )
            session.add(alert)
            session.flush()

            print(f"   ✓ Alert created: {alert.name}")
            print(f"     - Type: Category")
            print(f"     - Category: {alert.category}")
            print(f"     - Min Discount: 25%")
            print(f"     - Frequency: Instant")

            session.commit()

            # Create test deals that match the alert
            print("\n📦 Creating test deals...")
            test_deals = [
                {
                    "sku": "12345",
                    "store_id": "1001",
                    "title": "DeWalt 20V Cordless Drill",
                    "category": "Power Tools & Accessories",
                    "price": 49.99,
                    "price_was": 99.99,
                    "pct_off": 0.50,  # 50% off
                    "store_name": "Lowe's - Seattle",
                    "store_label": "Seattle WA Store #1001",
                    "store_state": "WA",
                    "product_url": "https://lowes.com/product/drill-123",
                    "image_url": "https://lowes.com/images/drill.jpg",
                },
                {
                    "sku": "67890",
                    "store_id": "1002",
                    "title": "Makita Impact Driver Set",
                    "category": "Power Tools",
                    "price": 59.99,
                    "price_was": 129.99,
                    "pct_off": 0.54,  # 54% off
                    "store_name": "Lowe's - Tacoma",
                    "store_label": "Tacoma WA Store #1002",
                    "store_state": "WA",
                    "product_url": "https://lowes.com/product/impact-456",
                    "image_url": "https://lowes.com/images/impact.jpg",
                },
            ]

            print(f"   ✓ Created {len(test_deals)} test deals that match the alert")
            for i, deal in enumerate(test_deals, 1):
                print(f"     {i}. {deal['title']} ({deal['pct_off']*100:.0f}% off)")

            # Process the deals (this will send the email)
            print("\n📧 Processing deals and sending email...")
            results = process_new_deals(session, test_deals)

            print(f"   ✓ Alerts matched: {results['alerts_matched']}")
            print(f"   ✓ Emails sent: {results['emails_sent']}")

            if results['emails_sent'] > 0:
                print("\n✅ SUCCESS! Email alert was sent to rob@redhatfunding.com")
                print("\nEmail Details:")
                print(f"   - To: rob@redhatfunding.com")
                print(f"   - Subject: 🤖 {len(test_deals)} New Deals - Power Tools Sale")
                print(f"   - Alert Type: Category (Power Tools)")
                print(f"   - Deals Included: {len(test_deals)}")
                return True
            else:
                print("\n❌ Email was not sent. Check logs for errors.")
                return False

    except Exception as e:
        LOGGER.error("Error in test: %s", e, exc_info=True)
        print(f"\n❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = setup_test_data()
    sys.exit(0 if success else 1)
