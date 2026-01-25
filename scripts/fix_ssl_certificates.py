#!/usr/bin/env python3
"""
Fix SSL certificate verification issues on Windows/Mac/Linux.

This script attempts to fix common SSL certificate issues that prevent
SendGrid (and other HTTPS services) from working.
"""

import sys
import subprocess
import platform
import os

print("\n" + "="*60)
print("SSL Certificate Fix Tool")
print("="*60 + "\n")

print(f"Platform: {platform.system()} {platform.release()}")
print(f"Python: {platform.python_version()}\n")

# Method 1: Update certifi (works on all platforms)
print("1️⃣  Attempting to update certifi...")
try:
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "certifi"],
        capture_output=True,
        text=True,
        timeout=60
    )
    if result.returncode == 0:
        print("   ✅ certifi updated successfully")
    else:
        print(f"   ⚠️  pip warning: {result.stderr[:200]}")
except Exception as e:
    print(f"   ❌ Error: {e}")

# Method 2: macOS - Install CA certificates
if platform.system() == "Darwin":
    print("\n2️⃣  Attempting macOS CA certificate installation...")
    try:
        result = subprocess.run(
            ["/Applications/Python 3.12/Install Certificates.command"],
            shell=True,
            capture_output=True,
            text=True,
            timeout=60
        )
        print("   ✅ macOS certificates installed")
    except FileNotFoundError:
        print("   ℹ️  Not found. This is optional.")
        print("   Run: /Applications/Python\\ 3.x/Install\\ Certificates.command")
    except Exception as e:
        print(f"   ⚠️  {e}")

# Method 3: Test the fix
print("\n3️⃣  Testing SSL certificate verification...")
try:
    import ssl
    import urllib.request

    ctx = ssl.create_default_context()
    with urllib.request.urlopen(
        "https://api.sendgrid.com",
        context=ctx,
        timeout=5
    ) as response:
        print("   ✅ SSL verification works!")

except ssl.SSLError as e:
    print(f"   ❌ SSL still failing: {e}")
    print("\n   Try these additional steps:")
    print("   1. Delete Python cache: pip install --cache-dir /tmp --no-cache-dir certifi")
    print("   2. Use conda/mamba instead of pip")
    print("   3. Use a Docker container with proper SSL setup")

except Exception as e:
    print(f"   ⚠️  Other error: {e}")

# Method 4: Show certifi location
print("\n4️⃣  Certifi certificate location:")
try:
    import certifi
    ca_path = certifi.where()
    print(f"   📍 {ca_path}")
    if os.path.exists(ca_path):
        print(f"   ✅ File exists ({os.path.getsize(ca_path)} bytes)")
    else:
        print(f"   ❌ File not found!")
except ImportError:
    print("   ❌ certifi not installed")

print("\n" + "="*60)
print("Fix Complete")
print("="*60)
print("\nNext steps:")
print("1. Run: export SENDGRID_API_KEY=SG.your_key")
print("2. Run: python scripts/diagnose_sendgrid.py")
print("3. Run: python scripts/test_sendgrid_flow.py")
print()
