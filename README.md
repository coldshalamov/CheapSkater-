# lowes-orwa-tracker

## Project summary
lowes-orwa-tracker is a store-scoped Lowe's clearance and price tracker focused on Oregon and Washington locations. It uses a DOM-first approach to read publicly visible product data without relying on hidden APIs.

## Legal & ethics
* Collect data only from publicly accessible pages.
* Schedule requests at a polite frequency and monitor load to avoid stressing Lowe's infrastructure.
* Review and comply with Lowe's website terms of service before running automated checks.

## Prerequisites (Windows)
1. Download and install [Python 3.11](https://www.python.org/downloads/release/python-3110/).
2. During installation, select **Add Python to PATH**.

## Quick start
Open **Windows PowerShell** in the project directory and run:

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install
```

## Configuration & environment
* `app/config.yml` — primary application configuration (store list, scrape intervals, output preferences).
* `.env` — sensitive credentials such as Telegram bot token and chat ID, or SendGrid API key and sender address.

## Run modes
* **Single run**: `python -m app.main --once`
* **Continuous loop**: `python -m app.main`

## Windows Task Scheduler (high-level preview)
1. Create a basic task and set the trigger you need.
2. Use the virtual environment interpreter directly, for example:
   `C:\path\to\lowes-orwa-tracker\.venv\Scripts\python.exe -m app.main`
3. Configure the working directory to the project root and finish the wizard. (Detailed steps will be documented later.)

## Outputs
* CSV exports under `/outputs/`.
* SQLite database file stored alongside other artifacts.
* Rotating log files written to `/logs/`.

## First-run expectations
The first execution should produce CSV rows, populate the SQLite database, and write at least one summary line in the logs.

## Troubleshooting teaser
Upcoming documentation will cover adjusting Playwright selectors when Lowe's changes page structure and tuning store context lists when coverage gaps appear.

---

## Example app/config.yml
```yaml
region: OR-WA
stores:
  - id: 1234
    label: Beaverton-OR
  - id: 5678
    label: Vancouver-WA
crawl:
  cadence_minutes: 20
  max_concurrency: 2
  per_store_delay_s: "5-9"  # randomized range
selectors:
  price: "span[data-testid='price']"
  clearance_badge: "div:has-text('Clearance')"
notifications:
  telegram_chat_id: null
  sendgrid_to: null
logging:
  level: INFO
  rotate_mb: 10
  keep: 7
```

## Data outputs
### CSV columns
`timestamp_iso`, `store_id`, `store_label`, `product_sku`, `product_url`, `title`, `price_current`, `price_was`, `clearance_flag`, `in_stock`, `aisle_bay`, `fetch_status`

### SQLite indices
- `UNIQUE(store_id, product_sku, timestamp)`
- `INDEX(product_sku, timestamp)`
- `INDEX(store_id, timestamp)`

## Hardening & Politeness
- Retries: per-item exponential backoff with jitter to keep a never-fails posture for the main loop.
- Randomized delays: 3–7 second baseline plus the configured `per_store_delay_s` window to avoid bursty load.
- Robots & ToS: honor robots.txt directives and keep concurrency bounded to respect the site.
- User-Agent: `lowes-orwa-tracker/1.0 (contact: you@example.com)` for transparent identification.
- Scope: no login flows, CAPTCHA bypassing, or hidden APIs—only DOM-first reads of public pages.

## macOS/Linux quick start
Open a terminal in the project directory and run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install
python -m app.main
```

## Windows Task Scheduler (exact settings)
When configuring the action step of a scheduled task, set:

- **Program/script**: `C:\path\to\lowes-orwa-tracker\.venv\Scripts\python.exe`
- **Add arguments**: `-m app.main`
- **Start in (IMPORTANT)**: `C:\path\to\lowes-orwa-tracker`
