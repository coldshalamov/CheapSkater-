# Email Alerts & Pricing Issues - Analysis & Fixes

## Current Problems

### 1. **Email System Not Configured**
- The pricing page says "Instant email notifications" for $10/each
- **BUT**: There's NO email sending system configured
- No SMTP server, no email service (SendGrid, Mailgun, etc.)
- Alerts are created in the database but never sent

### 2. **Pricing Confusion**
The pricing page shows:
- **FREE**: "View deals from last 24h" ❌ WRONG
- **PRO** ($50/mo): "Complete deal archive" ❌ WRONG  
- **Deal Alerts** ($10/each): "Instant email notifications" ❌ NOT WORKING

**Reality:**
- Everyone (free or paid) sees ALL deals (no time restriction)
- No features are actually paywalled
- Email alerts don't work (no email system)

### 3. **Backwards Logic**
You're right - it SHOULD be backwards:
- **FREE** should see complete archive (it's just data)
- **PRO** should get advanced features (exports, filters, etc.)
- **Alerts** should actually send emails (needs email system)

---

## What Needs to Be Fixed

### Fix 1: Update Pricing Page Copy

**Change FREE tier from:**
```
❌ View deals from last 24h
```

**To:**
```
✅ View all current deals
✅ Basic filters
✅ Save up to 5 deals
```

**Change PRO tier from:**
```
❌ Complete deal archive
```

**To:**
```
✅ Everything in FREE
✅ Unlimited saved deals
✅ Advanced search & filters
✅ Export to Excel
✅ Priority support
```

**Keep Deal Alerts as is, but add disclaimer:**
```
⚠️ Instant email notifications
   (Requires email configuration)
```

### Fix 2: Implement Email System

You need to choose an email service:

**Option A: SendGrid** (Recommended - Free tier: 100 emails/day)
```bash
pip install sendgrid
```

**Option B: Mailgun** (Free tier: 5,000 emails/month)
```bash
pip install mailgun
```

**Option C: AWS SES** (Cheapest for high volume)
```bash
pip install boto3
```

**Option D: SMTP** (Use your own email server)
```python
# Built into Python, no install needed
import smtplib
```

### Fix 3: Create Email Sending Service

Create `app/notifications/email_service.py`:

```python
import os
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

class EmailService:
    def __init__(self):
        self.api_key = os.getenv("SENDGRID_API_KEY")
        self.from_email = os.getenv("FROM_EMAIL", "alerts@gloorbot.com")
        self.client = SendGridAPIClient(self.api_key) if self.api_key else None
    
    def send_deal_alert(self, to_email: str, alert_name: str, deals: list):
        """Send a deal alert email."""
        if not self.client:
            print(f"⚠️  Email not configured - would send to {to_email}")
            return False
        
        # Build email HTML
        deals_html = ""
        for deal in deals:
            deals_html += f"""
            <div style="border: 1px solid #ddd; padding: 15px; margin: 10px 0;">
                <h3>{deal['title']}</h3>
                <p><strong>${deal['price']}</strong> (was ${deal['was_price']})</p>
                <p>{deal['pct_off']}% OFF</p>
                <a href="{deal['url']}">View Deal</a>
            </div>
            """
        
        html_content = f"""
        <html>
        <body>
            <h2>🔔 New Deal Alert: {alert_name}</h2>
            <p>We found {len(deals)} new deals matching your criteria!</p>
            {deals_html}
            <hr>
            <p><a href="https://your-site.com/notifications">Manage your alerts</a></p>
        </body>
        </html>
        """
        
        message = Mail(
            from_email=self.from_email,
            to_emails=to_email,
            subject=f"🔔 {len(deals)} New Deals: {alert_name}",
            html_content=html_content
        )
        
        try:
            response = self.client.send(message)
            return response.status_code == 202
        except Exception as e:
            print(f"❌ Email send failed: {e}")
            return False
```

### Fix 4: Create Alert Processing Background Job

Create `app/notifications/alert_processor.py`:

```python
"""Background job to process deal alerts and send notifications."""

from datetime import datetime, timedelta, timezone
from app.notifications.models import DealAlert, NotificationLog
from app.notifications.email_service import EmailService
from app.storage import repo

def process_alerts(session):
    """Check all active alerts and send notifications for matching deals."""
    email_service = EmailService()
    
    # Get all active alerts
    alerts = session.query(DealAlert).filter(
        DealAlert.is_active == True,
        DealAlert.email_enabled == True,
    ).all()
    
    for alert in alerts:
        # Get deals from last hour (or since last check)
        cutoff = alert.last_triggered_at or (datetime.now(timezone.utc) - timedelta(hours=1))
        
        # Query matching deals
        deals = repo.get_clearance_items(
            session,
            category=alert.category if alert.alert_type == "category" else None,
            # Add more filters based on alert criteria
        )
        
        # Filter by alert criteria
        matching_deals = []
        for deal in deals:
            # Check discount threshold
            if alert.min_discount and deal.get('pct_off', 0) < alert.min_discount:
                continue
            
            # Check price threshold
            if alert.max_price and deal.get('price', 999999) > alert.max_price:
                continue
            
            # Check keywords
            if alert.keywords:
                keywords = [k.strip().lower() for k in alert.keywords.split(',')]
                title_lower = deal.get('title', '').lower()
                if not any(kw in title_lower for kw in keywords):
                    continue
            
            matching_deals.append(deal)
        
        # Send email if there are matches
        if matching_deals:
            success = email_service.send_deal_alert(
                to_email=alert.user.email,
                alert_name=alert.name,
                deals=matching_deals
            )
            
            if success:
                # Log notification
                log = NotificationLog(
                    alert_id=alert.id,
                    user_id=alert.user_id,
                    sent_at=datetime.now(timezone.utc),
                    deal_count=len(matching_deals),
                    success=True,
                )
                session.add(log)
                
                # Update last triggered
                alert.last_triggered_at = datetime.now(timezone.utc)
                session.commit()
```

### Fix 5: Set Up Cron Job

Add to your deployment (Render, etc.):

```bash
# Run every 15 minutes
*/15 * * * * python -c "from app.notifications.alert_processor import process_alerts; from app.storage.db import make_session, get_engine; session = make_session(get_engine())(); process_alerts(session); session.close()"
```

Or use a proper task queue like Celery.

---

## Recommended Pricing Structure

### FREE (Current Default)
- ✅ View all current clearance deals
- ✅ Basic filters (category, state, discount)
- ✅ Save up to 5 deals
- ❌ No email alerts
- ❌ No export

### PRO - $19.99/month (Not $50!)
- ✅ Everything in FREE
- ✅ Unlimited saved deals
- ✅ Advanced filters
- ✅ Export to Excel
- ✅ 1 email alert included
- ✅ Priority support

### PREMIUM - $39.99/month
- ✅ Everything in PRO
- ✅ Up to 5 email alerts
- ✅ SMS notifications (if implemented)
- ✅ API access (if implemented)
- ✅ Custom integrations

### Add-on: Extra Alerts - $5/each
- For users who want more than their plan includes

---

## Implementation Checklist

### Phase 1: Fix Pricing Page (Easy - 10 min)
- [ ] Update FREE tier description
- [ ] Update PRO tier description  
- [ ] Change PRO price from $50 to $19.99
- [ ] Add email disclaimer

### Phase 2: Configure Email (Medium - 30 min)
- [ ] Choose email service (SendGrid recommended)
- [ ] Sign up for free tier
- [ ] Get API key
- [ ] Add to environment variables
- [ ] Test sending one email

### Phase 3: Build Email System (Hard - 2 hours)
- [ ] Create `email_service.py`
- [ ] Create `alert_processor.py`
- [ ] Test alert matching logic
- [ ] Test email sending

### Phase 4: Deploy Background Job (Medium - 30 min)
- [ ] Set up cron job or task queue
- [ ] Monitor for errors
- [ ] Test end-to-end flow

### Phase 5: Implement Paywall (Medium - 1 hour)
- [ ] Limit free users to 5 saved deals
- [ ] Require PRO for export
- [ ] Require PRO for alerts
- [ ] Add upgrade prompts

---

## Quick Fix for Pricing Page

Want me to update the pricing page right now to fix the confusing copy?

The main changes would be:
1. FREE: "View all current deals" (not "last 24h")
2. PRO: Lower price to $19.99 (not $50)
3. Add disclaimer that email alerts require configuration

This would at least make the pricing honest about what's currently available!
