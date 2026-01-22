# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

**CheapSkater** (aka **GloorBot**) is a two-component clearance deal tracking system:

1. **This Repository**: FastAPI web dashboard + API ingestion endpoint
2. **Separate Gloorbot Scraper**: Playwright-based automation (different repo)

**Critical**: The scraper lives in a separate repository. This repo only contains the dashboard, authentication, and API endpoints.

## Data Flow Architecture

```
Gloorbot Scraper (separate repo)
         ↓
POST /api/ingest/deals (API key auth)
         ↓
This Dashboard Repo (FastAPI)
         ↓
SQLite Database
         ↓
Users browse deals via web UI
```

## Running Locally

### Start the Dashboard
```bash
# Install dependencies
pip install -r requirements.txt
python -m playwright install chromium

# Run dashboard
uvicorn app.dashboard:app --reload
```

Dashboard starts at `http://localhost:8000`

**Expected behavior**: Local database will be empty unless you:
- Manually add test data via scripts
- Point Gloorbot scraper to localhost
- Download the production database from Render

### Running Tests
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_dashboard.py

# Run with verbose output
pytest -v

# Test directory is temporary (configured in pytest.ini)
# Temp files go to: .pytest_tmp/
```

## Key Environment Variables

Required variables (see `.env.example`):

```bash
# API Security
CHEAPSKATER_INGEST_API_KEY=     # Shared with Gloorbot scraper

# Database
CHEAPSKATER_DB_PATH=            # Path to SQLite file (Render: /var/data/orwa_lowes.sqlite)

# Authentication
CHEAPSKATER_SESSION_SECRET=     # Random string for session cookies

# Stripe (Subscriptions)
STRIPE_SECRET_KEY=              # sk_test_... or sk_live_...
STRIPE_PUBLISHABLE_KEY=         # pk_test_... or pk_live_...
STRIPE_WEBHOOK_SECRET=          # whsec_... (for subscription webhooks)
STRIPE_PRICE_BASIC=             # Stripe price ID
STRIPE_PRICE_PRO=               # Stripe price ID

# Email Alerts
SENDGRID_API_KEY=               # For deal notifications
SENDGRID_FROM=                  # Verified sender email
```

## Database Architecture

### SQLite with SQLAlchemy ORM

Location: `app/storage/`

**Main models** (`app/storage/models_sql.py`):
- `Store` - Retail locations (id, name, city, state, zip, region)
- `Item` - Product catalog (sku, title, category, urls)
- `Observation` - Price snapshots (store_id, sku, price, pct_off, ts_utc)
- `Alert` - Price change alerts
- `StorePriceHistory` - Historical price tracking
- `Quarantine` - Failed scraping attempts

**Auth models** (`app/auth/models.py`):
- `User` - User accounts (email, hashed passwords with PBKDF2)
- `Subscription` - Stripe subscription tracking
- `PaymentHistory` - Payment records

**Notification models** (`app/notifications/models.py`):
- `DealAlert` - User-defined alerts (category/keyword filters)
- `NotificationLog` - Sent notification tracking

### Database Operations

Primary interface: `app/storage/repo.py`

Key functions:
- `upsert_store()` - Insert or update stores
- `upsert_item()` - Insert or update items
- `record_observation()` - Record price observations
- `get_clearance_items()` - Query with filters (category, state, region, discount)

### Auto-Migration on Startup

`app/dashboard.py` runs `_ensure_schema_up_to_date()` which:
- Checks for required columns (`region` field for multi-region support)
- Auto-migrates if missing
- Backfills region data from ZIP codes

## Module Structure

### Core Modules

**`app/dashboard.py`** - Main FastAPI application
- Routes: `/`, `/export.xlsx`, `/api/clearance`, `/healthz`
- Serves Jinja2 templates from `app/templates/`
- Static files from `app/static/`
- Imports routers from auth, notifications, ingest, assistant

**`app/ingest.py`** - API endpoint for receiving deals
- `POST /api/ingest/deals` - Batch deal ingestion
- Requires `X-API-Key` header matching `CHEAPSKATER_INGEST_API_KEY`
- Processes `GloorbotDeal` objects from scraper
- Triggers notification matching after ingestion

**`app/auth/`** - Authentication & subscriptions
- `routes.py` - Login, registration, Stripe checkout
- `service.py` - Password hashing (PBKDF2), token generation
- `stripe_integration.py` - Subscription management
- `dependencies.py` - FastAPI dependencies (`get_current_user`)

**`app/notifications/`** - Deal alerts
- `routes.py` - Alert management UI/API
- `processor.py` - Matches deals against user alerts
- `email_service.py` - SendGrid integration
- Alert types: category-based, keyword-based

**`app/assistant/`** - Unlisted AI assistant subsite
- Chatbot interface for deal queries
- Uses `zai_service.py` for AI responses

### Supporting Modules

- `app/normalizers.py` - Text extraction (category names from breadcrumbs)
- `app/errors.py` - Custom exceptions
- `app/health.py` - Health check endpoint logic
- `app/monitoring.py` - Metrics collection
- `app/lowes_stores_wa_or.py` - WA/OR store definitions
- `app/lowes_stores_fl.py` - Florida store definitions

## Subscription Tiers

**Free Tier**:
- Browse last 5 days of deals
- 5 saved items limit
- No alerts

**Pro Access ($50/mo)**:
- Full historical archive
- Advanced filters
- Excel exports

**Paid Alerts ($10/mo each)**:
- Category or keyword-based
- Instant email notifications via SendGrid
- Discount % and price thresholds

## Store Regions

The system supports multiple regions:
- **WA/OR**: Washington (ZIP 980-994), Oregon (ZIP 970-979)
- **Florida**: ZIP codes 2200-2299

Region is auto-detected from ZIP code during ingestion and stored in the `region` column.

## Production Deployment

**Platform**: Render.com

**Key files**:
- `render.yaml` - Render service configuration
- Persistent disk mounted at `/var/data/`
- Database path: `/var/data/orwa_lowes.sqlite`

**Start command**:
```bash
uvicorn app.dashboard:app --host 0.0.0.0 --port $PORT
```

**Auto-deploy**: Pushes to GitHub trigger Render redeployment

## Scripts Directory

Utility scripts in `scripts/`:

**Database Management**:
- `create_admin.py` - Create admin user accounts
- `verify_admin.py` - Verify admin user exists
- `auto_migrate.py` - Database schema migration
- `merge_v6.py` - Merge database versions

**Store Management**:
- `generate_stores.py` - Generate store YAML configs
- `populate_florida_stores.py` - Add Florida stores
- `fetch_florida_addresses.py` - Geocode Florida locations
- `migrate_add_region.py` - Add region column to existing DBs

**Data Fixes**:
- `fix_existing_discounts.py` - Recalculate discount percentages

**Production Scripts**:
- `run-cheapskater.ps1` - PowerShell launcher
- `verify_readiness.py` - Pre-deployment validation

## Development Patterns

### Session Management
- Uses `SimpleSessionMiddleware` (custom implementation)
- Cookies signed with `CHEAPSKATER_SESSION_SECRET`
- Session helpers in `app/auth/dependencies.py`

### Database Sessions
```python
from app.storage.db import make_session, get_engine

engine = get_engine(db_path)
session_factory = make_session(engine)

with session_factory() as session:
    # Your database operations
    session.commit()
```

### FastAPI Dependency Injection
```python
from app.auth.dependencies import get_current_user

@router.get("/protected")
async def protected_route(user: User = Depends(get_current_user)):
    # user is guaranteed to be authenticated
    pass
```

### Adding New Deal Filters

To add filters to the dashboard query:

1. Update `app/storage/repo.py::get_clearance_items()` with new filter logic
2. Add query parameters to `app/dashboard.py` route handlers
3. Update template filters in `app/templates/dashboard.html`
4. Ensure indexes exist in `app/storage/models_sql.py` for performance

## Testing Strategy

Tests live in `tests/`

**Test database isolation**: pytest.ini configures temporary directory `.pytest_tmp/`

**Key test files**:
- `test_dashboard.py` - Dashboard routes and filtering
- `test_repo.py` - Database operations
- `test_florida_ingest.py` - Multi-region ingestion
- `test_discount_fix.py` - Discount calculation accuracy

**Fixtures**: Defined in `tests/conftest.py`

## Common Pitfalls

❌ **"Why is my local database empty?"**
- The scraper is a separate repository
- Production data is on Render's persistent disk
- You need to populate test data manually or run Gloorbot locally

❌ **"I added a feature but Stripe isn't working"**
- Check that all `STRIPE_*` env vars are set
- Use test keys (`sk_test_...`) for local development
- Webhook secret is only needed for subscription lifecycle events

❌ **"Notifications aren't sending"**
- Verify `SENDGRID_API_KEY` and `SENDGRID_FROM` are set
- Sender email must be verified in SendGrid dashboard
- Check `NotificationLog` table for delivery status

❌ **"Database locked errors"**
- Increase `DB_BUSY_TIMEOUT` environment variable (default: 30s)
- SQLite write-ahead log (WAL) mode is enabled for concurrency
- Render's persistent disk is single-instance (no multi-region writes)

## API Endpoints

**Public**:
- `GET /` - Dashboard homepage
- `GET /healthz` - Health check (returns `{"status": "ok"}`)
- `GET /api/clearance` - JSON deal data (with filters)
- `GET /export.xlsx` - Excel export (Pro tier only)

**Authentication**:
- `POST /auth/register` - Create account
- `POST /auth/login` - Login
- `POST /auth/logout` - Logout
- `GET /auth/subscribe` - Stripe checkout redirect
- `POST /auth/webhook` - Stripe webhook handler

**Notifications** (requires auth):
- `GET /notifications/alerts` - List user alerts
- `POST /notifications/alerts` - Create new alert
- `PATCH /notifications/alerts/{id}` - Update alert
- `DELETE /notifications/alerts/{id}` - Delete alert

**Ingestion** (requires API key):
- `POST /api/ingest/deals` - Batch deal upload from Gloorbot

## Logging

Structured logging via `app/logging_config.py`

Logs to: `logs/` directory

**Log files**:
- `logs/app.log` - Application logs
- `logs/metrics_summary.json` - Performance metrics
- `logs/zip_cursor.json` - Scraper state (not in this repo)

## Important Constants

**Store ZIP ranges**:
- Washington: 980-994
- Oregon: 970-979
- Florida: 2200-2299

**Timeouts**:
- Database busy timeout: 30s (configurable via `DB_BUSY_TIMEOUT`)
- Health check staleness: 120 minutes (configurable via `DASHBOARD_HEALTH_MAX_STALE_MINUTES`)

**Subscription limits**:
- Free tier: 5 saved items, 5-day deal history
- Pro tier: Unlimited saved items, full archive access
