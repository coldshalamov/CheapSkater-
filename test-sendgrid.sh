#!/bin/bash
# Test SendGrid Integration Script
# Usage: ./test-sendgrid.sh [SENDGRID_API_KEY] [SENDGRID_FROM]

set -e

echo ""
echo "========================================"
echo "SendGrid Integration Test Launcher"
echo "========================================"
echo ""

# Set API key if provided as argument
if [ ! -z "$1" ]; then
    export SENDGRID_API_KEY="$1"
    echo "Using provided API key"
else
    if [ -z "$SENDGRID_API_KEY" ]; then
        echo "ERROR: No SendGrid API key provided!"
        echo ""
        echo "Usage:"
        echo "  ./test-sendgrid.sh <API_KEY> [SENDER_EMAIL]"
        echo ""
        echo "Or set environment variable:"
        echo "  export SENDGRID_API_KEY=SG.your_key_here"
        echo "  ./test-sendgrid.sh"
        echo ""
        exit 1
    else
        echo "Using SENDGRID_API_KEY environment variable"
    fi
fi

# Set sender email if provided
if [ ! -z "$2" ]; then
    export SENDGRID_FROM="$2"
else
    export SENDGRID_FROM="deals@gloorbot.com"
fi

# Check for database
if [ ! -f "cheapskater.db" ]; then
    echo "WARNING: cheapskater.db not found in current directory"
    echo "The script may fail if the database doesn't exist"
    echo ""
fi

echo ""
echo "Configuration:"
echo "  API Key: ${SENDGRID_API_KEY:0:10}... (hidden)"
echo "  From: $SENDGRID_FROM"
echo "  To: rob@redhatfunding.com"
echo ""
echo "Running test script..."
echo ""

python scripts/test_sendgrid_flow.py
