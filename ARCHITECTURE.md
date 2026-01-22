# CheapSkater Architecture

## System Overview

CheapSkater is a **distributed clearance tracking system** with two separate components:

### 1. **Dashboard/API (This Repo)**
- **Location**: `CheapSkater-` repository
- **Hosting**: Render.com web service
- **Purpose**: 
  - Serves the web dashboard for users to browse deals
  - Provides API endpoints for deal ingestion
  - Manages user authentication, subscriptions (Stripe), and alerts
- **Database**: SQLite on Render's **paid persistent disk** storage
- **Key Endpoints**:
  - `GET /` - Public dashboard
  - `POST /api/ingest/deals` - Receives deals from Gloorbot (secured with API key)
  - `/auth/*` - User authentication
  - `/alerts/*` - Deal alert management

### 2. **Scraper (Gloorbot)**
- **Location**: Separate repository (not in this repo)
- **Hosting**: Runs independently (possibly on different infrastructure)
- **Purpose**: 
  - Scrapes Lowe's stores for clearance deals
  - Sends discovered deals to the dashboard via API
- **Technology**: Playwright-based automation
- **Target Stores**: 
  - Washington (980-994)
  - Oregon (970-979)
  - Florida (2200-2299)

## Data Flow

```
┌─────────────────┐
│   Gloorbot      │
│   (Scraper)     │
│  - Playwright   │
│  - Store scan   │
└────────┬────────┘
         │
         │ POST /api/ingest/deals
         │ (with API key)
         ▼
┌─────────────────────────────┐
│  CheapSkater Dashboard      │
│  (This Repo - Render.com)   │
│  ┌─────────────────────┐   │
│  │  FastAPI Backend    │   │
│  │  - Ingest API       │   │
│  │  - Auth/Stripe      │   │
│  │  - Alert matching   │   │
│  └──────────┬──────────┘   │
│             │               │
│  ┌──────────▼──────────┐   │
│  │  SQLite Database    │   │
│  │  (Persistent Disk)  │   │
│  │  - Deals            │   │
│  │  - Users            │   │
│  │  - Alerts           │   │
│  └─────────────────────┘   │
└─────────────┬───────────────┘
              │
              │ Web UI
              ▼
         ┌─────────┐
         │  Users  │
         └─────────┘
```

## Key Configuration

### Environment Variables (Dashboard)
- `CHEAPSKATER_INGEST_API_KEY`: Secures the ingestion endpoint (shared with Gloorbot)
- `CHEAPSKATER_DB_PATH`: Path to SQLite database on persistent disk
- `STRIPE_SECRET_KEY`: For subscription management
- `SENDGRID_API_KEY`: For email alerts

### Database Storage
- **Type**: SQLite (via SQLAlchemy ORM)
- **Location**: Render.com persistent disk (paid feature)
- **Path**: Controlled by `CHEAPSKATER_DB_PATH` environment variable
- **Persistence**: Data survives deployments and restarts

## Local Development

When running locally:

1. **Dashboard only** (this is what you're doing):
   ```bash
   python -m uvicorn app.dashboard:app --reload
   ```
   - Runs the web interface on `http://localhost:8000`
   - Uses local SQLite database
   - **Database will be empty** unless you:
     - Manually add test data
     - Point to a copy of the production database
     - Have Gloorbot running locally and configured to send to localhost

2. **With local Gloorbot** (separate repo):
   - Configure Gloorbot to send to `http://localhost:8000/api/ingest/deals`
   - Set matching `CHEAPSKATER_INGEST_API_KEY` in both repos

## Why the Database is Empty Locally

The local database is empty because:

1. **Gloorbot runs separately** - It's not part of this repository
2. **Production data is on Render** - The persistent disk is only accessible to the Render deployment
3. **No automatic sync** - Local and production databases are completely separate

To populate your local database, you can:
- Create test data with scripts
- Download a copy of the production database from Render
- Run Gloorbot locally pointed at your local instance

## Production Deployment

1. **Push to GitHub**: Changes are pushed to the repository
2. **Render auto-deploys**: Render detects the push and redeploys
3. **Persistent disk mounts**: Database remains intact across deployments
4. **Gloorbot continues**: Scraper keeps sending deals to the production API

## Important Notes for AI Agents

⚠️ **Critical Understanding**:
- This repo **does not contain the scraper**
- The database is **populated via API calls** from an external service (Gloorbot)
- Running this repo locally **will show an empty dashboard** unless:
  - You manually populate test data, OR
  - You configure Gloorbot to send to your local instance, OR
  - You download the production database

- The production database lives on **Render's paid persistent disk**
- Local development uses a **separate, empty SQLite file**
