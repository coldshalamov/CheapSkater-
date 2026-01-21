# Quick Start: Adding Florida Support

This is a quick reference for setting up Florida store tracking in CheapSkater.

## Step 1: Migrate Your Database

```bash
python scripts/migrate_add_region.py
```

This adds the `region` column to your existing database.

## Step 2: Add Florida Stores

### Option A: Manual Entry
Edit `app/lowes_stores_fl.py` and add stores:

```python
LOWES_STORES_FL: dict[str, dict[str, str]] = {
    "1234": {
        "name": "LOWE'S OF MIAMI, FL",
        "address": "123 Main St, Miami, FL 33101",
        "city": "Miami",
        "state": "FL",
        "zip": "33101",
    },
}
```

### Option B: Use Helper Script
```bash
# Interactive mode
python scripts/populate_florida_stores.py

# From CSV
python scripts/populate_florida_stores.py --csv my_florida_stores.csv
```

## Step 3: Configure Your Scraper

Create a Florida-specific configuration or add FL ZIPs to your existing config:

```yaml
retailers:
  lowes:
    enabled: true
    zips:
      - "33101"  # Miami
      - "33139"  # Miami Beach
      - "33301"  # Fort Lauderdale
```

## Step 4: Update Your Scraper Code

Ensure your scraper sets `region="FL"` when creating stores:

```python
from app.lowes_stores_fl import LOWES_STORES_FL

# When processing Florida stores
store_info = LOWES_STORES_FL.get(store_id)
if store_info:
    repo.upsert_store(
        session,
        store_id=store_id,
        name=store_info["name"],
        zip_code=store_info["zip"],
        city=store_info["city"],
        state=store_info["state"],
        region="FL"  # Important!
    )
```

And when creating observations:

```python
observation = Observation(
    # ... other fields ...
    region="FL",  # Set region for Florida stores
)
```

## Step 5: Use the UI

1. Open the dashboard in your browser
2. Use the **Region** dropdown to select "Florida"
3. Browse Florida-specific clearance deals!

## Region Detection Helper

You can automatically detect region from state:

```python
def get_region_from_state(state: str) -> str:
    """Get region code from state abbreviation."""
    if state in ("WA", "OR"):
        return "WA_OR"
    elif state == "FL":
        return "FL"
    return "WA_OR"  # default
```

## Troubleshooting

**Q: I don't see Florida stores in the UI**
- Check that stores have `region="FL"` in the database
- Verify observations have `region="FL"`
- Run the migration script if you haven't already

**Q: How do I run separate scrapers for each region?**
- Create two config files: `config_wa_or.yml` and `config_fl.yml`
- Run them separately or use a scheduler

**Q: Can I mix regions in one scraper run?**
- Yes, but make sure to set the correct `region` for each store based on its state

## Next Steps

See [MULTI_REGION_GUIDE.md](MULTI_REGION_GUIDE.md) for complete documentation.
