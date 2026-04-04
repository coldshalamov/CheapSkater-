# 🚀 How to Launch CheapSkater Frontend

## ⚠️ IMPORTANT: This is the Frontend Site Only

This repository is **NOT** a scraper anymore. It's the **frontend dashboard** that displays clearance deals.

The scraping functionality has been moved to a separate coordinator/scraper repository.

## Correct Way to Launch

### Windows

Run this file from the root directory:

```bash
LAUNCH_SITE.bat
```

This will:
1. Activate the virtual environment
2. Start the uvicorn server on port 9000
3. Open your browser to http://localhost:9000

### Manual Launch (All Platforms)

```bash
# Activate virtual environment
# Windows:
.venv\Scripts\activate

# Mac/Linux:
source .venv/bin/activate

# Start the server
python -m uvicorn app.dashboard:app --host 0.0.0.0 --port 9000 --reload
```

## What This Site Does

This is a **FastAPI web application** that:
- Displays clearance deals from a SQLite database
- Provides user authentication and subscriptions
- Offers email alerts for deals
- Has an admin panel for managing deals and users

## Database

The site reads from `orwa_lowes.sqlite` which should be populated by the separate scraper/coordinator service.

## Environment Variables

Create a `.env` file with:

```env
# Database
CHEAPSKATER_DB_PATH=orwa_lowes.sqlite

# Stripe (for payments)
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# SendGrid (for emails)
SENDGRID_API_KEY=SG...
SENDGRID_FROM_EMAIL=noreply@yourdomain.com
SENDGRID_FROM_NAME=CheapSkater

# Admin
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=<hashed_password>
```

## Useful Scripts

- `scripts/purge_old_data.py` - Clean up old database entries
- `scripts/create_admin.py` - Create admin user
- `scripts/test_email.py` - Test email configuration

## Deployment

This site is deployed on Render.com. See `DEPLOYMENT_GUIDE.md` for details.

## Need Help?

- Check `ARCHITECTURE.md` for system overview
- Check `AUTH_AND_PAYWALL_GUIDE.md` for authentication details
- Check `ADMIN_FEATURES.md` for admin panel documentation
