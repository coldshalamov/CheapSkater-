# Lowebot (formerly CheapSkater) - Agent Instructions

## System Overview

**Lowebot** is a distributed Lowe's clearance tracking system split across two repositories:

1.  **Dashboard/Site** (This Repo: `D:\GitHub\Telomere\CheapSkater-`)
    *   **Role**: The "Frontend" or "Site". Hosts the web dashboard, user authentication, and the ingestion API.
    *   **Tech**: FastAPI, Jinja2.

2.  **Scraper/Coordinator** (Other Repo: `D:\GitHub\Telomere\Gloorbot`)
    *   **Role**: The "Backend" or "Scraper". Runs the Playwright bots, coordinates jobs, and sends data to the Dashboard.
    *   **Tech**: Python, Playwright.

## Critical: Repository Boundaries

### ✅ This Repository (`CheapSkater-`) Has:
- **The Website**: `dashboard.py`, templates, CSS.
- **The Receiver API**: `ingest.py` (receives data from Gloorbot).
- **User Auth**: Stripe, Login, Admin logic.
- **Notifications**: Email alerts service.

### ❌ This Repository Does NOT Have:
- **The Scraper Logic**: That is in `D:\GitHub\Telomere\Gloorbot`.
- **The Coordinator**: Also in `Gloorbot`.
- **Production Database**: Stored on Render persistent disk (download to view locally).

## Architecture Diagram

```
┌───────────────────────────────────────┐
│  Gloorbot Scraper / Coordinator       │
│  (Path: D:\GitHub\Telomere\Gloorbot)  │
│  - Playwright Scrapers                │
│  - Orchestrator Backend               │
└──────────────────┬────────────────────┘
                   │
                   │ POST /api/ingest/deals
                   │ (Data Pushed to Dashboard)
                   ▼
┌───────────────────────────────────────┐
│  Lowebot Dashboard / Site             │
│  (Path: D:\GitHub\Telomere\CheapSkater-)
│  ┌────────────────────────┐           │
│  │  FastAPI Ingest API    │           │
│  │  Auth & Web UI         │           │
│  └───────────┬────────────┘           │
│              │                        │
│  ┌───────────▼────────────┐           │
│  │  SQLite Database       │           │
│  │  (Render Persistent)   │           │
│  └────────────────────────┘           │
└───────────────────────────────────────┘
```

## Why Local Database is Empty

**Expected Behavior**: When running `dashboard.py` locally, the database is empty.

**Reason**:
- Production data lives on Render.
- The Scraper (Gloorbot) runs in a separate process/server.
- They are decoupled systems connected by the API.

**To populate local database**:
1. Add test data manually with scripts
2. Configure Gloorbot to send to `http://localhost:8000/api/ingest/deals`
3. Download production database from Render (if needed)

## Key Environment Variables

| Variable | Purpose |
|----------|---------|
| `CHEAPSKATER_DB_PATH` | Path to SQLite database file |
| `CHEAPSKATER_INGEST_API_KEY` | Secures API endpoint (shared with Gloorbot) |
| `CHEAPSKATER_SESSION_SECRET` | Session cookie encryption |
| `STRIPE_SECRET_KEY` | Stripe payment processing |
| `STRIPE_PUBLISHABLE_KEY` | Stripe client-side key |
| `SENDGRID_API_KEY` | Email notifications |

## Common Agent Mistakes

### ❌ Mistake 1: Looking for scraper code
**Wrong**: "Let me find the Playwright scraper in this repo"
**Right**: "The scraper is in a separate Gloorbot repository"

### ❌ Mistake 2: Expecting local database to have data
**Wrong**: "The database is broken, there are no deals"
**Right**: "The local database is empty because Gloorbot runs separately"

### ❌ Mistake 3: Trying to run the scraper
**Wrong**: "Let me run `python -m app.main` to scrape deals"
**Right**: "This repo only has the dashboard. Gloorbot handles scraping."

### ❌ Mistake 4: Confusing local and production
**Wrong**: "Why isn't the production database updating?"
**Right**: "Production is on Render with persistent disk. Local is separate."

## Development Workflow

### Running Locally
```bash
# Start the dashboard
python -m uvicorn app.dashboard:app --reload

# Access at http://localhost:8000
# Database will be empty unless manually populated
```

### Testing Without Gloorbot
1. Create test users: `python scripts/create_test_user.py`
2. Add test deals: Manually insert into database or create a script
3. Test UI, authentication, alerts, etc.

### Deployment to Render
1. Push changes to GitHub
2. Render auto-deploys
3. Persistent disk preserves database across deployments
4. Gloorbot continues sending deals to production API

## File Structure

```
CheapSkater-/
├── app/
│   ├── dashboard.py          # Main FastAPI app
│   ├── ingest.py            # API endpoint for receiving deals
│   ├── auth/                # Authentication system
│   ├── notifications/       # Email alert matching
│   ├── templates/           # Jinja2 HTML templates
│   └── static/              # CSS, JS, images
├── scripts/                 # Utility scripts
├── tests/                   # Test suite
├── .env                     # Local environment variables
└── requirements.txt         # Python dependencies
```

## Agent Decision Tree

```
Is the task about...

├─ Scraping Lowe's stores?
│  └─ ❌ Wrong repo - Gloorbot handles this
│
├─ Dashboard UI/UX?
│  └─ ✅ Edit templates in app/templates/
│
├─ User authentication?
│  └─ ✅ Edit app/auth/
│
├─ Deal ingestion API?
│  └─ ✅ Edit app/ingest.py
│
├─ Email alerts?
│  └─ ✅ Edit app/notifications/
│
├─ Database schema?
│  └─ ✅ Edit app/models.py
│
└─ Why is local database empty?
   └─ ℹ️ This is expected - see "Why Local Database is Empty"
```

## Testing Checklist

Before making changes, verify:
- [ ] Is this a dashboard/API change? (✅ This repo)
- [ ] Is this a scraping change? (❌ Wrong repo)
- [ ] Will this affect production data? (⚠️ Be careful)
- [ ] Can I test without Gloorbot? (Usually yes)
- [ ] Do I need to update environment variables? (Check .env)

## Quick Commands

```bash
# Run dashboard locally
uvicorn app.dashboard:app --reload

# Run tests
pytest

# Create admin user
python scripts/create_admin.py

# Verify database
python scripts/verify_db.py
```

## Production Details

- **Hosting**: Render.com web service
- **Database**: SQLite on paid persistent disk
- **URL**: (Check Render dashboard)
- **Deployment**: Auto-deploy from GitHub main branch
- **Logs**: Available in Render dashboard

## When to Ask User

Ask the user if:
1. You need access to the Gloorbot repository
2. You need to modify production database directly
3. You need Render credentials or access
4. You're unsure if a change affects the scraper vs dashboard
5. You need production environment variables

## Summary for All Agents

**Remember**: This repo is the **dashboard/API only**. The scraper (Gloorbot) is separate. Local database being empty is **normal and expected**. Focus on UI, authentication, API endpoints, and alert features when working in this repository.
