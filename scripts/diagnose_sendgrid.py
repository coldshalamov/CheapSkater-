#!/usr/bin/env python3
"""
Diagnostic script to troubleshoot SendGrid integration issues.

This script will:
1. Check if SendGrid library is installed
2. Verify API key format and presence
3. Test SSL certificate verification
4. Attempt a test API call to SendGrid
5. Provide detailed error messages
"""

import sys
import os

print("\n" + "="*60)
print("SendGrid Integration Diagnostics")
print("="*60 + "\n")

# Step 1: Check if SendGrid is installed
print("1️⃣  Checking SendGrid library installation...")
try:
    import sendgrid
    from sendgrid.helpers.mail import Mail, Email, To, Content
    print("   ✅ sendgrid library is installed")
    print(f"   Version: {sendgrid.__version__ if hasattr(sendgrid, '__version__') else 'unknown'}")
except ImportError as e:
    print(f"   ❌ Failed to import sendgrid: {e}")
    print("\n   Solution: Run 'pip install sendgrid>=6.10.0'")
    sys.exit(1)

# Step 2: Check API key
print("\n2️⃣  Checking SendGrid API key...")
api_key = os.getenv("SENDGRID_API_KEY", "").strip()
if not api_key:
    print("   ❌ SENDGRID_API_KEY environment variable is NOT set")
    print("\n   Solution:")
    print("      export SENDGRID_API_KEY=SG.your_actual_key")
    print("      python scripts/diagnose_sendgrid.py")
    sys.exit(1)

if not api_key.startswith("SG."):
    print(f"   ⚠️  API key doesn't start with 'SG.' (unusual format)")
    print(f"   First 10 chars: {api_key[:10]}")
else:
    print(f"   ✅ API key format looks valid (starts with SG.)")
    print(f"   Length: {len(api_key)} characters")

# Step 3: Check sender email
print("\n3️⃣  Checking sender email configuration...")
sender_email = os.getenv("SENDGRID_FROM", "")
if not sender_email:
    print("   ⚠️  SENDGRID_FROM not set, using default: deals@gloorbot.com")
    sender_email = "deals@gloorbot.com"
else:
    print(f"   ✅ Sender email configured: {sender_email}")

# Step 4: Test SSL certificates
print("\n4️⃣  Testing SSL certificate verification...")
try:
    import ssl
    import urllib.request

    # Try to verify SSL certificates work
    print("   Testing connection to api.sendgrid.com...")
    ctx = ssl.create_default_context()
    with urllib.request.urlopen("https://api.sendgrid.com", context=ctx, timeout=5) as response:
        print("   ✅ SSL certificate verification successful")
except ssl.SSLError as e:
    print(f"   ❌ SSL certificate verification failed: {e}")
    print("\n   This is a Python environment issue. Solutions:")
    print("      1. Install certificates: /Applications/Python\\ 3.x/Install\\ Certificates.command")
    print("      2. Update: pip install --upgrade certifi")
    print("      3. Use development environment with proper SSL setup")
except Exception as e:
    print(f"   ⚠️  Connection test failed: {e}")

# Step 5: Test SendGrid API call
print("\n5️⃣  Testing SendGrid API connection...")
try:
    sg = sendgrid.SendGridAPIClient(api_key=api_key)

    print("   Attempting to send test email...")
    message = Mail(
        from_email=Email(sender_email, "GloorBot Test"),
        to_emails=To("rob@redhatfunding.com"),
        subject="🤖 SendGrid Test Email",
        html_content=Content("text/html", "<h1>Test Email</h1><p>If you received this, SendGrid is working!</p>"),
    )

    response = sg.send(message)

    print(f"\n   SendGrid Response:")
    print(f"   Status Code: {response.status_code}")
    print(f"   Headers: {dict(response.headers)}")

    if response.status_code in (200, 201, 202):
        print("\n   ✅ SUCCESS! Email was sent to SendGrid")
        print("\n   Next steps:")
        print("      1. Check your inbox at rob@redhatfunding.com")
        print("      2. Check SendGrid Mail Activity dashboard")
        print("      3. If not received, the sender email may not be verified")
    else:
        print(f"\n   ❌ Unexpected status code: {response.status_code}")
        try:
            error_body = response.body
            print(f"   Error body: {error_body}")
        except:
            pass

except sendgrid.SendGridAPIError as e:
    print(f"\n   ❌ SendGrid API Error: {e}")
    print(f"   Status code: {e.http_error.status_code if hasattr(e, 'http_error') else 'unknown'}")
    print(f"   Error message: {e.http_error.body if hasattr(e, 'http_error') else str(e)}")

    if "401" in str(e) or "Unauthorized" in str(e):
        print("\n   This is an authentication error. Check:")
        print("      1. Is SENDGRID_API_KEY valid and not expired?")
        print("      2. Is the API key actually starting with 'SG.'?")
        print("      3. Try generating a new API key in SendGrid dashboard")

except Exception as e:
    print(f"\n   ❌ Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
print("Diagnostics Complete")
print("="*60 + "\n")
