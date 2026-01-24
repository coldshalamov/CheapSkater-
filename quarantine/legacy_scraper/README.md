# Legacy scraper quarantine

This folder holds code and tooling from the original **combined** repo that ran a Playwright-based scraper (`python -m app.main`) alongside the dashboard.

The production scraper now lives in the separate **Gloorbot** repository and pushes deals into this repo via the ingest API. The dashboard/site entrypoint remains:

- `uvicorn app.dashboard:app`
- Local launcher: `LAUNCH_SITE.bat`
- Render: `render.yaml` `startCommand` uses `uvicorn app.dashboard:app`

Nothing in this folder should be imported or required by the running site. It is kept temporarily for reference and can be deleted later once you’re comfortable nothing is needed.
