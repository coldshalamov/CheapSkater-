# SendGrid Email Alert Testing

I've created a complete test suite to simulate the email alert flow and verify your SendGrid integration is working correctly.

## 📁 What I Created

### 1. **Test Script** (`scripts/test_sendgrid_flow.py`)
The main Python script that:
- Verifies SendGrid is configured
- Creates a test user (rob@redhatfunding.com)
- Creates a category-based deal alert
- Generates synthetic test deals matching the alert criteria
- Triggers the notification processor
- Sends an actual email through SendGrid

### 2. **Test Launchers**
- **Windows**: `test-sendgrid.bat` - Batch script wrapper
- **Linux/Mac**: `test-sendgrid.sh` - Bash script wrapper

### 3. **Documentation**
- **`SENDGRID_TEST_GUIDE.md`** - Detailed setup and troubleshooting guide
- **`TEST_SENDGRID_README.md`** - This file

## 🚀 Quick Start

### Step 1: Get Your SendGrid API Key

1. Sign up at [SendGrid](https://sendgrid.com) (free tier available)
2. Go to **Settings** → **API Keys**
3. Create a new API key (it will start with `SG.`)
4. Copy the key

⚠️ **Important**: Your `SENDGRID_FROM` email must be verified in SendGrid settings.

### Step 2: Run the Test

#### Option A: Direct Python (Recommended)
```bash
# Set your credentials and run
export SENDGRID_API_KEY=SG.your_key_here
export SENDGRID_FROM=deals@gloorbot.com
python scripts/test_sendgrid_flow.py
```

#### Option B: Using Batch Script (Windows)
```bash
test-sendgrid.bat SG.your_key_here deals@gloorbot.com
```

#### Option C: Using Shell Script (Linux/Mac)
```bash
chmod +x test-sendgrid.sh
./test-sendgrid.sh SG.your_key_here deals@gloorbot.com
```

#### Option D: Use .env File
Create `.env` in the project root:
```
SENDGRID_API_KEY=SG.your_key_here
SENDGRID_FROM=deals@gloorbot.com
CHEAPSKATER_SESSION_SECRET=any_random_string
```

Then simply:
```bash
python scripts/test_sendgrid_flow.py
```

## 📧 What Gets Tested

The test simulates a real-world email alert flow:

```
User Creates Alert
        ↓
Scraper Sends Deals
        ↓
System Matches Deals to Alert
        ↓
SendGrid Sends Email
        ↓
User Receives: rob@redhatfunding.com
```

### Email Content
The test email includes:
- **2 synthetic power tool deals** with 50%+ discounts
- **Beautiful HTML template** with:
  - Product images
  - Prices and discount percentages
  - Store locations
  - Direct product links
  - "View Deal" buttons
  - Alert management links

## ✅ Success Indicators

### Console Output Shows:
```
✅ SendGrid is configured
✓ User created: rob@redhatfunding.com
✓ Alert created: Power Tools Sale
✓ Created 2 test deals that match the alert
✓ Alerts matched: 1
✓ Emails sent: 1

✅ SUCCESS! Email alert was sent to rob@redhatfunding.com
```

### Email Verification:
1. Check SendGrid Dashboard → **Mail Activity**
2. Search for `rob@redhatfunding.com`
3. You should see an email with subject: `🤖 2 New Deals - Power Tools Sale`
4. Status should be "Delivered" (or "Processed" for test keys)

## 🔍 How It Works

### 1. User Setup
- Creates a test user with email `rob@redhatfunding.com`
- Gives them a PRO subscription

### 2. Alert Configuration
- **Type**: Category-based
- **Category**: "Power Tools"
- **Min Discount**: 25%
- **Frequency**: Instant (sends immediately)
- **Status**: Active

### 3. Test Deals
Two synthetic deals are created that match the alert:
- DeWalt 20V Cordless Drill (50% off, $49.99 from $99.99)
- Makita Impact Driver Set (54% off, $59.99 from $129.99)

### 4. Notification Processing
The `process_new_deals()` function:
1. Finds all active alerts
2. Matches each deal against alert criteria
3. Deduplicates (won't send for same deal twice)
4. Sends email if configured
5. Logs to database for audit trail

## 📊 Database Changes

After running the test, your database will have:

**Users table**:
```
email:               rob@redhatfunding.com
is_verified:         True
is_active:           True
display_name:        Rob Test
```

**Deal Alerts table**:
```
name:                Power Tools Sale
alert_type:          category
category:            Power Tools
min_discount:        0.25 (25%)
frequency:           instant
email_enabled:       True
is_active:           True
```

**Notification Logs table**:
```
Records for each deal/alert combination sent
Shows email_sent status and timestamps
```

## 🧪 Testing Different Scenarios

### Test Keyword Alerts
Modify the test script to use keyword matching:
```python
alert = DealAlert(
    ...
    alert_type=NotificationType.KEYWORD,
    keywords="drill, saw, power",  # Changed from category
    ...
)
```

### Test Different Discount Thresholds
```python
alert.min_discount = 0.75  # 75% or more off
```

### Test State Filtering
```python
alert.states = "WA,OR"  # Only Washington and Oregon
```

## 🐛 Troubleshooting

### SendGrid Not Configured
```
❌ SendGrid not configured!
   Set SENDGRID_API_KEY environment variable to enable email.
```
**Solution**:
- Verify `SENDGRID_API_KEY` is set with a valid SendGrid key
- Run: `python -c "import os; print(os.getenv('SENDGRID_API_KEY'))"`

### Email Not Sent (but no error)
**Check**:
1. Is `SENDGRID_FROM` a verified sender in SendGrid? (required!)
2. Check logs: `tail -f logs/app.log | grep -i sendgrid`
3. Verify email format: `rob@redhatfunding.com` is valid

### Database Locked
```
DatabaseLockedError: database is locked
```
**Solution**:
- Close any other connections to the database
- Increase `DB_BUSY_TIMEOUT` environment variable

### Module Not Found
```
ModuleNotFoundError: No module named 'app'
```
**Solution**:
- Run from project root: `cd d:\GitHub\Telomere\CheapSkater-`
- Ensure requirements installed: `pip install -r requirements.txt`

## 📝 Integration with Real Scraper

Once verified, the system works like this in production:

1. **Gloorbot Scraper** sends deals via: `POST /api/ingest/deals`
2. **Dashboard** receives deals and calls `process_new_deals()`
3. **For each active alert**, it:
   - Matches deals against criteria
   - Sends instant notifications via SendGrid
   - Or queues for daily/weekly digest
4. **Users receive emails** with beautiful HTML templates

## 📚 Related Code

Key files involved in the email alert system:

- **Email service**: `app/notifications/email_service.py` - Sends emails
- **Processor**: `app/notifications/processor.py` - Matches alerts to deals
- **Models**: `app/notifications/models.py` - DealAlert, NotificationLog
- **Routes**: `app/notifications/routes.py` - Alert management UI
- **Ingestion**: `app/ingest.py` - Receives deals from scraper

## ✨ Next Steps

After confirming the test works:

1. **Create user alerts** via the dashboard UI
2. **Verify delivery** in SendGrid Mail Activity
3. **Monitor logs** for any delivery failures
4. **Set up monitoring** for failed sends

## 💡 Advanced: Manual Email Sending

If you want to manually send an alert email, you can use the service directly:

```python
from app.notifications.email_service import send_deal_alert_email

success = send_deal_alert_email(
    to_email="rob@redhatfunding.com",
    alert_name="Power Tools Sale",
    deals=[
        {
            "title": "DeWalt Drill",
            "price": 49.99,
            "price_was": 99.99,
            "pct_off": 0.50,
            "category": "Power Tools",
            "sku": "12345",
            "store_label": "Lowe's Seattle",
            "store_state": "WA",
            "product_url": "https://lowes.com/product/123",
        }
    ],
    alert_type="category",
    criteria="Power Tools",
)
```

## 🎯 Summary

| Item | Details |
|------|---------|
| **Test User** | rob@redhatfunding.com |
| **Alert Type** | Category (Power Tools) |
| **Min Discount** | 25% |
| **Test Deals** | 2 synthetic power tools |
| **Email Subject** | 🤖 2 New Deals - Power Tools Sale |
| **Database** | Tracked in notification_logs table |
| **Verification** | SendGrid Mail Activity → search email |

Good luck! If the test succeeds, your SendGrid integration is working perfectly! 🚀
