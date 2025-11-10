# CheapSkater WA/OR Lowe's Clearance Tracker

CheapSkater continuously scrapes every Lowe's store in Washington (ZIPs 980-994) and Oregon (ZIPs 970-979) for building-material clearance deals. The Playwright-driven backend writes observations to SQLite, publishes atomic CSV/Excel exports, and serves a responsive FastAPI dashboard at `http://localhost:8000`.

## Prerequisites

* Python 3.11+ (tested on Linux and Windows)
* Node is **not** required—Playwright downloads Chromium automatically
* SQLite is bundled with Python

After cloning the repository run:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium
```

## Quick verify

```bash
python -m venv .venv
. .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
python -m playwright install chromium
pytest -q
```

## Configuration

Key settings in `app/config.yml`:

```yaml
material_keywords:
  - roofing
  - drywall
  - insulation
  # ... add or remove as needed

quarantine_retention_days: 30  # Auto-cleanup invalid records

schedule:
  minutes: 180

alerts:
  pct_drop: 0.25
```

## First-time discovery

Generate the monitored catalog and ZIP list directly from lowes.com. Both commands only need to be run when you want to refresh the catalog or store list.

```bash
python -m app.main --discover-categories
python -m app.main --discover-stores
```

## Running the scraper

* One-off cycle (all WA/OR ZIPs, three-at-a-time concurrency):

  ```bash
  python -m app.main --once
  ```

* Continuous scheduler (default every 180 minutes) with the dashboard enabled:

  ```bash
  python -m app.main --dashboard
  ```

* Override ZIPs or categories when needed:

  ```bash
  python -m app.main --once --zip 98101,97223 --categories "roof|drywall"
  ```

The run summary prints to stdout in the form:

```
cycle ok | retailer=lowes | zips=<N> | items=<M> | alerts=<K> | duration=<seconds>
```

## Dashboard

The FastAPI dashboard lives at `http://localhost:8000` and provides:

* State filter (`?state=WA` or `?state=OR`)
* Category dropdown seeded with common building-material departments
* Sortable, mobile-friendly table highlighting percent-off and price
* Export to Excel (`/export.xlsx`) and JSON API (`/api/clearance`)
* `GET /healthz` health check endpoint for uptime monitors

Static assets are served from `app/static` and the templates live under `app/templates`.

## Data pipeline

1. Playwright sets store context for each ZIP code while reusing a single browser instance per run.
2. Only building-material categories (roofing, drywall, insulation, lumber, etc.) are processed.
3. Prices are validated and must fall between `$0.01` and `$100,000`. Rows outside the range are quarantined in a dedicated table for investigation.
4. Observations, alerts, and quarantine entries are stored in `orwa_lowes.sqlite`. Key indexes cover `clearance`, `category`, `zip`, and store lookups for fast dashboard queries.
5. After a successful run the denormalised export at `outputs/orwa_items.csv` is replaced atomically using a temporary file swap.
6. The optional Excel export is generated on-demand via the dashboard.

## CLI switches

* `--discover-categories` — crawl the public navigation/department pages and build `catalog/all.lowes.yml`.
* `--discover-stores` — collect every WA/OR store ZIP and write `catalog/wa_or_stores.yml`.
* `--once` — run a single scrape cycle.
* `--dashboard` — launch the FastAPI dashboard alongside the scheduler.
* `--zip 98101,97223` — override the discovered ZIP list (comma separated).
* `--categories "roof|insulation"` — regex filter applied to catalog names.
* `--concurrency N` — number of ZIPs processed concurrently (defaults to `3`).

## Alerts

Alerts are emitted when:

1. A `(store_id, sku)` transitions into clearance for the first time.
2. The new price drops by at least `alerts.pct_drop` relative to the previous observation.
3. An absolute drop threshold (global or category-specific) defined in `app/config.yml` is exceeded.

Notifications are pushed via the configured transports in `.env` (Telegram or SendGrid). Without credentials the alerts remain in the SQLite `alerts` table and are logged.

## Health check and CSV

If `healthcheck_url` is set in `app/config.yml`, a `GET` is issued after every successful run. The CSV export lives at `outputs/orwa_items.csv` and now includes a `state` column in addition to the existing Lowe's metadata.

## Manual verification

See `TESTING.md` for a checklist covering scraper sanity checks, dashboard expectations, and export validation.
Run `python -m app.main --probe --zip 98101` after any Lowe's UI changes to validate selectors.
