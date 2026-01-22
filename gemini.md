# CheapSkater - Gemini Agent Guide

## 🎯 Core Concept

**CheapSkater** = Dashboard + Scraper (separate repos)

This repo = **Dashboard only** (FastAPI web app on Render.com)

## 🏗️ System Architecture

```
[Gloorbot Scraper]  →  POST /api/ingest/deals  →  [CheapSkater Dashboard]  →  [Users]
(Separate Repo)         (with API key)              (This Repo)
```

## ✅ What's in THIS Repository

| Component | Description |
|-----------|-------------|
| **FastAPI Dashboard** | Web UI for browsing deals |
| **API Ingestion** | `POST /api/ingest/deals` endpoint |
| **Authentication** | User accounts, sessions, password hashing |
| **Stripe Integration** | $50/mo Pro, $10/mo per alert |
| **Email Alerts** | SendGrid notifications |
| **Templates** | Jinja2 HTML, CSS, JavaScript |

## ❌ What's NOT in This Repository

| Component | Where It Lives |
|-----------|----------------|
| **Scraper (Gloorbot)** | Separate repository |
| **Playwright automation** | Gloorbot repo |
| **Production database** | Render.com persistent disk |
| **Store scanning logic** | Gloorbot repo |

## 🔑 Critical Understanding

### Local Database is Empty - This is NORMAL

**Why?**
- Production data → Render.com paid persistent disk
- Gloorbot scraper → Separate service
- Local instance → Separate empty database

**Not a bug!** This is expected behavior.

### Data Flow

1. **Gloorbot** (separate service) scrapes Lowe's stores
2. **Gloorbot** sends deals via `POST /api/ingest/deals` (with API key)
3. **Dashboard** (this repo) receives and stores deals
4. **Users** browse deals via web interface

## 🚀 Quick Start

```bash
# Run dashboard locally
python -m uvicorn app.dashboard:app --reload

# Access at http://localhost:8000
# Database will be empty (this is expected)
```

## 📁 Key Files

```
app/
├── dashboard.py          # Main FastAPI application
├── ingest.py            # API endpoint for receiving deals
├── auth/                # User authentication
│   ├── middleware.py
│   └── utils.py
├── notifications/       # Email alert system
│   ├── processor.py
│   └── email_service.py
├── templates/           # Jinja2 HTML
└── static/             # CSS, JS, images
```

## 🔐 Environment Variables

```bash
CHEAPSKATER_DB_PATH              # SQLite database path
CHEAPSKATER_INGEST_API_KEY       # API security (shared with Gloorbot)
CHEAPSKATER_SESSION_SECRET       # Session encryption
STRIPE_SECRET_KEY                # Payment processing
STRIPE_PUBLISHABLE_KEY           # Stripe client key
SENDGRID_API_KEY                 # Email notifications
```

## 🚨 Common Gemini Mistakes

### Mistake #1: Looking for Scraper
```
❌ "Let me check the Playwright scraper code"
✅ "The scraper is in a separate Gloorbot repository"
```

### Mistake #2: Empty Database Panic
```
❌ "The database is broken, no deals found"
✅ "Local database is empty because Gloorbot runs separately"
```

### Mistake #3: Trying to Run Scraper
```
❌ "Running python -m app.main to scrape"
✅ "This repo only has the dashboard, not the scraper"
```

### Mistake #4: Production Confusion
```
❌ "Why isn't production updating?"
✅ "Production is on Render with persistent disk, separate from local"
```

## 🧪 Testing Without Gloorbot

You can test most features without the scraper:

1. **Create test users**: `python scripts/create_test_user.py`
2. **Add test deals**: Manually insert into SQLite
3. **Test UI**: Browse, filter, search functionality
4. **Test auth**: Login, logout, sessions
5. **Test alerts**: Email notification matching

## 🎯 Decision Matrix

| Task | Action |
|------|--------|
| Fix dashboard UI | ✅ Edit `app/templates/` |
| Add authentication feature | ✅ Edit `app/auth/` |
| Modify deal ingestion | ✅ Edit `app/ingest.py` |
| Change email alerts | ✅ Edit `app/notifications/` |
| Update scraping logic | ❌ Wrong repo (Gloorbot) |
| Fix empty database | ℹ️ Expected behavior |

## 🔄 Deployment Flow

```
1. Push to GitHub
   ↓
2. Render auto-deploys
   ↓
3. Persistent disk preserves database
   ↓
4. Gloorbot continues sending deals
```

## 📊 Database Schema

```python
# Main tables (in app/models.py)
- ClearanceItem      # Deals from Gloorbot
- User               # User accounts
- DealAlert          # Email alert rules
- SavedDeal          # User-saved deals
```

## 🛠️ Useful Commands

```bash
# Development
uvicorn app.dashboard:app --reload

# Testing
pytest

# Database
python scripts/verify_db.py
python scripts/create_admin.py

# Check logs (production)
# → Render dashboard
```

## 🧠 Mental Model for Gemini

Think of this system as:

```
Kitchen (Gloorbot)  →  Delivers food  →  Restaurant (Dashboard)  →  Customers
(Separate place)       (via API)          (This repo)              (Users)
```

You're working in the **restaurant** (dashboard).
The **kitchen** (scraper) is elsewhere.
Food arrives via **delivery** (API).

## ⚠️ Before Making Changes

Ask yourself:
1. Is this about the **dashboard/UI**? → ✅ This repo
2. Is this about **scraping**? → ❌ Wrong repo
3. Will this affect **production data**? → ⚠️ Be careful
4. Can I test **without Gloorbot**? → Usually yes

## 🎓 Key Takeaways

1. **This repo = Dashboard only** (not the scraper)
2. **Empty local database = Normal** (Gloorbot is separate)
3. **Production = Render.com** (persistent disk)
4. **API ingestion** = How deals arrive from Gloorbot
5. **Focus on**: UI, auth, alerts, API endpoints

## 📞 When to Ask User

- Need access to Gloorbot repository
- Need to modify production database directly
- Need Render credentials
- Unsure if change affects scraper vs dashboard
- Need production environment variables

## 🎯 TL;DR for Gemini

**Dashboard repo** (this) + **Scraper repo** (separate) = Complete system

Local database empty? **Expected.**

Looking for scraper code? **Wrong repo.**

Focus on: **UI, auth, API, alerts.**

Production: **Render.com with persistent disk.**

---

**Remember**: You're working on the **web interface**, not the **data collection**. The scraper lives elsewhere and sends data via API.
