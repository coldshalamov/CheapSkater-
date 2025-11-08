# lowes-orwa-tracker

Windows-first Lowe's tracker that scrapes public DOM pages with Playwright (Chromium), sets a store by ZIP, and records price/clearance data for a fixed catalog of building-material categories.

## Prerequisites (Windows)
1. Install **Python 3.12 (64-bit)** via the Microsoft Store or python.org (enable “Add python.exe to PATH” or use the `py` launcher).
2. Install Microsoft Edge or Google Chrome (Playwright downloads Chromium behind the scenes).
3. Clone this repo and open **PowerShell** in the project root.

## Quick start
```powershell
python -m venv .venv
\.venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install

# One-time discovery of catalog URLs & WA/OR ZIPs
python -m app.main --discover-categories
python -m app.main --discover-stores

# Sanity-check the first catalog entry at one store (uses the discovered catalog)
python -m app.main --probe --zip 98101

# Run a single scrape cycle (all discovered stores + catalog URLs)
python -m app.main --once
```
- `--probe` sets the store, opens the first catalog URL, and asserts that cards, titles, and prices are present. It fails fast if selectors drift.
- `--once` runs the entire loop (all ZIPs + catalog URLs) one time. A successful cycle prints:
  ```
  cycle ok | retailer=lowes | zips={N} | items={M} | alerts={K} | duration={XX}s
  ```
- `python -m app.main` enters the scheduled loop (default every 180 minutes via APScheduler).

## Task Scheduler
1. **Task Scheduler → Create Task…**  
2. **Triggers** → **On a schedule** → Daily → Repeat every **3 hours** (for 1 day) → Enabled.  
3. **Actions** → **New…**  
   - Program/script: `C:\path\to\repo\.venv\Scripts\python.exe`  
   - Add arguments: `-m app.main`  
   - Start in: `C:\path\to\repo`  
4. Check **Run whether user is logged on or not**, save, then **Run** to test.

## Configuration
- `app/config.yml` — retailer toggle, discovery file paths, scrape cadence, alert thresholds, output paths, and healthcheck URL.
- `catalog/all.lowes.yml` — populated by `python -m app.main --discover-categories`; contains every Lowe's `/c/` and `/pl/` URL found in the public navigation/department pages.
- `catalog/wa_or_stores.yml` — populated by `python -m app.main --discover-stores`; contains every Washington & Oregon Lowe's ZIP pulled from the public store locator UI.
- `app/selectors.py` — the only place CSS selectors live. Update these constants if Lowe’s changes markup.
- `.env` (copy from `.env.example`) — Telegram/SendGrid credentials plus optional overrides like `LOG_LEVEL`, `HTTP_PROXY`, or a custom User-Agent. If no transport is configured, alerts are logged only.

## What each run does
1. Discovery (optional) builds `catalog/all.lowes.yml` and `catalog/wa_or_stores.yml` directly from the Lowe's public DOM—no hand curation required.
2. For every ZIP in the resolved list, Playwright opens lowes.com, sets the store, confirms the header badge, and logs `store=<name> zip=<zip>`.
3. Each catalog URL is visited with polite waits and page-by-page pagination. If a page renders zero product cards, a `SelectorChangedError` is raised for that category but other pages continue.
4. Every card supplies: `sku`, `title`, `category`, `price`, `price_was`, `pct_off`, `availability`, `image_url`, `product_url`, `store_id`, `store_name`, `zip`, and `clearance` (badge keywords or `% off >= alerts.pct_drop`).
5. Observations and Alerts are appended to SQLite (`orwa_lowes.sqlite`). The denormalised latest snapshot is rewritten to `outputs/orwa_items.csv` each cycle with these exact columns:
   `ts_utc, retailer, store_id, store_name, zip, sku, title, category, price, price_was, pct_off, availability, product_url, image_url`
6. Logs go to both console and `logs/app.log`. The summary line above is always printed. If `healthcheck_url` is non-empty, the scraper performs a `GET` after a successful cycle.

## CLI switches
- `--discover-categories` — crawl the public navigation/department pages and write `catalog/all.lowes.yml`.
- `--discover-stores` — crawl the public store locator UI and write `catalog/wa_or_stores.yml`.
- `--once` — run a single cycle.
- `--probe` — quick markup sanity check (optionally accepts `--zip`).
- `--zip 98101,97204` — override the ZIP list (comma separated).
- `--categories "roof|insulation"` — regex/substring filter applied to catalog names (case-insensitive).

## Alerts
Alerts fire when:
1. Clearance flips from False/None to True for a `(store_id, sku)` pair.
2. The new price is less than or equal to `last_price * (1 - alerts.pct_drop)`.

If Telegram (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) or SendGrid (`SENDGRID_API_KEY`, `SENDGRID_FROM`, `SENDGRID_TO`) credentials are present, alerts are sent; otherwise they remain in the SQLite `alerts` table and the logs.

## Troubleshooting
- **Selector drift** → run `python -m app.main --probe --zip 98101 --categories flooring` to confirm the failure and adjust `app/selectors.py`.
- **Store context fails** → ensure the Lowe’s site allows you to change stores manually and that the `STORE_BADGE` selector still matches the header badge.
- **Zero cards scraped** → validate the category URL in `catalog/all.lowes.yml` still renders products for the selected store.
- **Playwright missing browsers** → rerun `python -m playwright install` inside the virtual environment.

The program is intentionally boring: one catalog file, one selector module, one orchestration loop. Keep those three sources of truth up to date and the rest runs on rails.
