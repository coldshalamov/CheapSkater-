# Manual Verification Checklist

Use this checklist when validating a production build of the WA/OR Lowe's clearance tracker.

## Scraper sanity
- [ ] Run `python -m app.main --discover-categories` to confirm catalog discovery succeeds.
- [ ] Run `python -m app.main --discover-stores` and ensure the resulting YAML contains ZIP codes from both WA and OR ranges.
- [ ] Execute `python -m app.main --once` and verify the summary line reports non-zero items for multiple ZIPs.
- [ ] Inspect `logs/app.log` for any `SelectorChangedError`, `StoreContextError`, or quarantine inserts that require investigation.

## Database & exports
- [ ] Open `orwa_lowes.sqlite` and confirm `observations`, `alerts`, and `quarantine` tables contain recent timestamps.
- [ ] Check `outputs/orwa_items.csv` to ensure the `state` column is present and values align with the ZIP prefixes.
- [ ] Trigger the dashboard export (`http://localhost:8000/export.xlsx`) and confirm the workbook opens with column headers and at least one data row.

## Dashboard UI
- [ ] Navigate to `http://localhost:8000` and verify the All/New Today navigation highlights the active view.
- [ ] Apply the state filter for WA and OR; confirm the table updates and the badge in the header reflects the selection.
- [ ] Use the category dropdown to filter to a specific building-material department (e.g., Roofing) and ensure only matching rows remain.
- [ ] Click table headers to sort by price and percent-off; verify the order toggles between ascending and descending.

## API & health check
- [ ] Request `http://localhost:8000/api/clearance?scope=all&state=WA` and ensure the JSON payload reports the expected item count.
- [ ] Call `http://localhost:8000/healthz` and confirm the response is `{"status": "ok"}`.
