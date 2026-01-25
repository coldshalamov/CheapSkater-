# SendGrid Email Integration Troubleshooting

You're getting **no emails to display** in SendGrid because the integration isn't working yet. Here's how to diagnose and fix the issue.

## 🔍 Common Issues Found

Based on your logs, there are **two main problems**:

### Issue 1: SSL Certificate Verification Error

```
ERROR app.notifications.email_service: Email send error: <urlopen error [SSL: CERTIFICATE_VERIFY_FAILED] ...>
```

This is a Python environment issue, NOT a SendGrid issue. Your Python installation can't verify SSL certificates.

### Issue 2: 401 Unauthorized Error

```
ERROR app.notifications.email_service: Email send error: HTTP Error 401: Unauthorized
```

This means either:
- The API key is invalid
- The API key is incorrectly formatted
- The API key is expired or revoked

---

## ✅ Step-by-Step Fix

### Step 1: Verify Your API Key

1. Go to [SendGrid Dashboard](https://app.sendgrid.com/)
2. Click **Settings** → **API Keys**
3. Look for an API key starting with `SG.`
4. **Copy the full key** (it should be ~100 characters)
5. Make sure you can see the full key (sometimes it's hidden)

**If you don't have an API key:**
1. Click **Create API Key**
2. Name it (e.g., "Lowebot Development")
3. Select **Restricted Access**
4. Grant these permissions:
   - **Mail Send** → Full Access
   - **Mail Send** (toggle on)
5. Click **Create & Update**
6. **Copy the key immediately** (you can only see it once!)

### Step 2: Fix SSL Certificate Issue

This is common in local Python environments. Choose ONE solution:

#### Solution A: Update certifi (Recommended)
```bash
pip install --upgrade certifi
```

#### Solution B: Install CA certificates (macOS)
If using macOS, run the installer:
```bash
/Applications/Python\ 3.x/Install\ Certificates.command
```

#### Solution C: Disable SSL verification (Development Only)
Edit `app/notifications/email_service.py`, find this line:
```python
sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
```

Add SSL verification bypass (NOT for production):
```python
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

import ssl
ssl._create_default_https_context = ssl._create_unverified_context

sg = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)
```

**⚠️ WARNING**: Never do this in production!

### Step 3: Verify Sender Email

Your `SENDGRID_FROM` email must be verified in SendGrid:

1. In SendGrid dashboard, go **Settings** → **Sender Authentication**
2. Check if `deals@gloorbot.com` is listed and verified
3. **If not verified:**
   - Click **Verify a Sender**
   - Enter the email address
   - Check your email for a verification link
   - Click the link to verify

**If you don't own that domain:**
- Use an email you control (e.g., your personal Gmail)
- Or use SendGrid's default sender email

### Step 4: Run Diagnostics

Run the diagnostic script I created:

```bash
# Set your API key first
export SENDGRID_API_KEY=SG.your_actual_key_here
export SENDGRID_FROM=your-verified-email@example.com

# Run diagnostics
python scripts/diagnose_sendgrid.py
```

This will:
1. ✅ Check if SendGrid is installed
2. ✅ Verify your API key format
3. ✅ Test SSL certificates
4. ✅ Send a test email to rob@redhatfunding.com
5. ✅ Show detailed error messages if anything fails

### Step 5: Test the Full Flow

Once diagnostics pass, run the test script:

```bash
python scripts/test_sendgrid_flow.py
```

Expected output:
```
✅ SendGrid is configured
✓ User created: rob@redhatfunding.com
✓ Alert created: Power Tools Sale
✓ Alerts matched: 1
✓ Emails sent: 1

✅ SUCCESS! Email alert was sent to rob@redhatfunding.com
```

---

## 🔧 Detailed Solutions by Error

### Error: "SSL: CERTIFICATE_VERIFY_FAILED"

**What it means**: Python can't verify SendGrid's SSL certificate.

**Solutions (in order):**
1. Update certificates: `pip install --upgrade certifi`
2. On Mac: `/Applications/Python\ 3.x/Install\ Certificates.command`
3. Use a proper Python environment (Anaconda, poetry, venv)
4. For development: Disable SSL verification (see above)

### Error: "HTTP Error 401: Unauthorized"

**What it means**: SendGrid rejected your API key.

**Check**:
1. Is the API key valid? (Must start with `SG.`)
2. Is the API key the complete key? (Sometimes it's truncated in display)
3. Has the API key expired? (Try creating a new one)
4. Is there a typo? (Copy/paste directly without spaces)

**Fix**:
```bash
# Print the key to verify it's set correctly
python -c "import os; print(os.getenv('SENDGRID_API_KEY'))"

# Should print something like: SG.abc123xyz...
# If empty, the env variable isn't set
```

### Error: "SendGrid not configured"

**What it means**: `SENDGRID_API_KEY` environment variable is not set.

**Solution**:
```bash
# Set the environment variable
export SENDGRID_API_KEY=SG.your_key_here

# Verify it's set
echo $SENDGRID_API_KEY

# Run test
python scripts/test_sendgrid_flow.py
```

### Email sent but not received

**Check in order**:
1. ✅ SendGrid Mail Activity shows it as "Delivered"
2. ✅ Check rob@redhatfunding.com inbox
3. ✅ Check spam/junk folder
4. ✅ Is `SENDGRID_FROM` a verified sender email?
5. ✅ Is rob@redhatfunding.com a valid email address?

**If status is "Bounced"** or **"Dropped"**:
- Click the email in Mail Activity for bounce reason
- Usually means: invalid email address, recipient blocked, etc.

---

## 📋 Complete Setup Checklist

Before testing, verify ALL of these:

- [ ] SendGrid account created at sendgrid.com
- [ ] API key generated (starts with `SG.`)
- [ ] API key has **Mail Send** permissions
- [ ] Sender email is verified in SendGrid settings
- [ ] `SENDGRID_API_KEY` environment variable is set
- [ ] `SENDGRID_FROM` environment variable is set (or use default)
- [ ] Python packages updated: `pip install --upgrade certifi sendgrid`
- [ ] Run diagnostics: `python scripts/diagnose_sendgrid.py`
- [ ] Diagnostics show "✅ SUCCESS"

---

## 🚀 Setting Environment Variables

### Windows (PowerShell)
```powershell
$env:SENDGRID_API_KEY="SG.your_key_here"
$env:SENDGRID_FROM="deals@gloorbot.com"
python scripts/test_sendgrid_flow.py
```

### Windows (Command Prompt)
```cmd
set SENDGRID_API_KEY=SG.your_key_here
set SENDGRID_FROM=deals@gloorbot.com
python scripts/test_sendgrid_flow.py
```

### Linux/Mac (Bash)
```bash
export SENDGRID_API_KEY=SG.your_key_here
export SENDGRID_FROM=deals@gloorbot.com
python scripts/test_sendgrid_flow.py
```

### Using .env File (Permanent)
Create file: `d:\GitHub\Telomere\CheapSkater-\.env`

```ini
SENDGRID_API_KEY=SG.your_key_here
SENDGRID_FROM=deals@gloorbot.com
SENDGRID_FROM_NAME=GloorBot Deal Alerts
CHEAPSKATER_SESSION_SECRET=any_random_string_for_sessions
```

Then run without setting env vars:
```bash
python scripts/test_sendgrid_flow.py
```

---

## 🛠️ Advanced: Testing Specific Components

### Test 1: Can Python reach SendGrid?

```bash
export SENDGRID_API_KEY=SG.your_key
python -c "
import sendgrid
sg = sendgrid.SendGridAPIClient(api_key='$SENDGRID_API_KEY')
print('✅ Connected to SendGrid')
"
```

### Test 2: Is the sender email verified?

```bash
export SENDGRID_API_KEY=SG.your_key
python -c "
import sendgrid
sg = sendgrid.SendGridAPIClient(api_key='$SENDGRID_API_KEY')
response = sg.client.senders.get()
print('Verified senders:', response.body)
"
```

### Test 3: Send raw test email

```bash
export SENDGRID_API_KEY=SG.your_key
python -c "
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content

sg = sendgrid.SendGridAPIClient(api_key='$SENDGRID_API_KEY')
message = Mail(
    from_email=Email('deals@gloorbot.com', 'Test'),
    to_emails=To('rob@redhatfunding.com'),
    subject='Raw Test',
    html_content='<h1>Test</h1>'
)
response = sg.send(message)
print(f'Status: {response.status_code}')
"
```

---

## 📞 Still Not Working?

1. ✅ Run the diagnostic script: `python scripts/diagnose_sendgrid.py`
2. ✅ Share the error output
3. ✅ Check SendGrid Mail Activity for any activity
4. ✅ Verify all env variables are set: `env | grep SENDGRID`

## Key Files

- **Diagnostic script**: `scripts/diagnose_sendgrid.py`
- **Test script**: `scripts/test_sendgrid_flow.py`
- **Email service**: `app/notifications/email_service.py`
- **Logs**: `logs/app.log` (search for "SendGrid")

Good luck! 🚀
