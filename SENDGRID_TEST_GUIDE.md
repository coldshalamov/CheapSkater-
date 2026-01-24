# SendGrid Integration Test Guide

I've created a test script that simulates a complete email alert flow to verify your SendGrid integration is working.

## What the Test Does

The script (`scripts/test_sendgrid_flow.py`) will:

1. ✅ Check if SendGrid is configured
2. ✅ Create a test user with email `rob@redhatfunding.com`
3. ✅ Create a category-based deal alert (for "Power Tools")
4. ✅ Create synthetic test deals that match the alert criteria
5. ✅ Trigger the notification processor
6. ✅ Send an actual email to `rob@redhatfunding.com` if everything is configured

## Prerequisites

Before running the test, you need to set up your SendGrid credentials:

### Option 1: Using .env file (recommended for development)

Create a `.env` file in the project root:

```bash
SENDGRID_API_KEY=SG.your_api_key_here
SENDGRID_FROM=deals@gloorbot.com
SENDGRID_FROM_NAME=GloorBot Deal Alerts
CHEAPSKATER_DB_PATH=cheapskater.db
CHEAPSKATER_SESSION_SECRET=your_secret_key_here
```

### Option 2: Export environment variables

```bash
# Linux/Mac
export SENDGRID_API_KEY=SG.your_api_key_here
export SENDGRID_FROM=deals@gloorbot.com
export SENDGRID_FROM_NAME=GloorBot Deal Alerts

# Windows PowerShell
$env:SENDGRID_API_KEY="SG.your_api_key_here"
$env:SENDGRID_FROM="deals@gloorbot.com"
$env:SENDGRID_FROM_NAME="GloorBot Deal Alerts"
```

## Getting Your SendGrid API Key

1. Go to [SendGrid](https://sendgrid.com)
2. Log in or create an account
3. Navigate to **Settings** → **API Keys**
4. Click **Create API Key**
5. Give it a name like "Lowebot Development"
6. Copy the key (it starts with `SG.`)

**IMPORTANT**: Your `SENDGRID_FROM` email must be verified in SendGrid. By default, only the email associated with your SendGrid account is verified. To add more sender emails:
1. Go to **Settings** → **Sender Authentication**
2. Add and verify your sender email address

## Running the Test

### From the project directory:

```bash
# Using Python directly
python scripts/test_sendgrid_flow.py

# Or with full environment variables
SENDGRID_API_KEY=SG.xxx SENDGRID_FROM=deals@gloorbot.com python scripts/test_sendgrid_flow.py

# Windows PowerShell
$env:SENDGRID_API_KEY="SG.xxx"
$env:SENDGRID_FROM="deals@gloorbot.com"
python scripts/test_sendgrid_flow.py
```

## Expected Output

### ✅ Success (SendGrid configured and email sent):

```
============================================================
SendGrid Integration Test
============================================================
✅ SendGrid is configured

📝 Creating test user...
   ✓ User created: rob@redhatfunding.com

🔔 Creating deal alert...
   ✓ Alert created: Power Tools Sale
     - Type: Category
     - Category: Power Tools
     - Min Discount: 25%
     - Frequency: Instant

📦 Creating test deals...
   ✓ Created 2 test deals that match the alert
     1. DeWalt 20V Cordless Drill (50% off)
     2. Makita Impact Driver Set (54% off)

📧 Processing deals and sending email...
   ✓ Alerts matched: 1
   ✓ Emails sent: 1

✅ SUCCESS! Email alert was sent to rob@redhatfunding.com

Email Details:
   - To: rob@redhatfunding.com
   - Subject: 🤖 2 New Deals - Power Tools Sale
   - Alert Type: Category (Power Tools)
   - Deals Included: 2
```

### ❌ Error (SendGrid not configured):

```
============================================================
SendGrid Integration Test
============================================================
❌ SendGrid not configured!
   Set SENDGRID_API_KEY environment variable to enable email.
```

## What Gets Sent

The email will include:

- **Subject**: `🤖 2 New Deals - Power Tools Sale`
- **From**: Your configured `SENDGRID_FROM` address
- **To**: `rob@redhatfunding.com`
- **Body**:
  - Beautiful HTML template with deal cards
  - Product images (if URLs are available)
  - Discount percentages highlighted
  - Prices and store locations
  - Direct links to view deals
  - Alert management links in footer

## Checking SendGrid Activity

After running the test, check if the email was sent:

1. Log in to [SendGrid Mail Activity](https://app.sendgrid.com/email_activity)
2. Search for `rob@redhatfunding.com`
3. You should see an email with subject `🤖 2 New Deals - Power Tools Sale`

**Note**: If using a test API key, emails may be simulated rather than actually delivered. Check your SendGrid dashboard for delivery status.

## Troubleshooting

### Problem: "SendGrid not configured"
- **Solution**: Check that `SENDGRID_API_KEY` is set and starts with `SG.`
- Verify the env variable is actually being read: `python -c "import os; print(os.getenv('SENDGRID_API_KEY'))"`

### Problem: Email not received
- **Check 1**: Verify `SENDGRID_FROM` is a verified sender email in SendGrid
- **Check 2**: Look for bounce/delivery errors in SendGrid Mail Activity
- **Check 3**: Check spam folder for rob@redhatfunding.com
- **Check 4**: Review application logs for errors: `tail -f logs/app.log`

### Problem: Script fails with database error
- **Solution**: Make sure `CHEAPSKATER_DB_PATH` points to a valid SQLite database
- The database should already exist from running the application
- Or run migrations first: `python scripts/auto_migrate.py`

### Problem: "No module named app"
- **Solution**: Make sure you're running from the project root directory
- Check that you have `python -m pip install -r requirements.txt` installed

## Next Steps

If the test succeeds:
1. Email alerts are working! 🎉
2. Users can now create paid deal alerts
3. When deals are ingested from the scraper, they'll receive instant notifications

If you want to create additional alerts for testing:
- Use the dashboard UI at `http://localhost:8000` after logging in
- Or create more using `scripts/test_sendgrid_flow.py` (modify the script)
