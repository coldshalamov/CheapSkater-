# Multi-Region Support - README Addition

## New Feature: Multi-Region Support

CheapSkater now supports tracking clearance deals from multiple regions! You can now monitor stores in:
- **Washington & Oregon** (original functionality)
- **Florida** (new!)

### Quick Start

1. **Migrate your database** (one-time setup):
   ```bash
   python scripts/migrate_add_region.py
   ```

2. **Add Florida stores** (if needed):
   ```bash
   # Interactive mode
   python scripts/populate_florida_stores.py
   
   # Or from CSV
   python scripts/populate_florida_stores.py --csv florida_stores.csv
   ```

3. **Use the region selector** in the web dashboard:
   - Open the dashboard
   - Use the "Region" dropdown to switch between regions
   - Filter by state within each region

### Key Features

- **Separate regions**: Keep WA/OR and FL stores completely separate
- **Single database**: All regions use the same database infrastructure
- **Easy switching**: Toggle between regions with a single click
- **Backward compatible**: Existing WA/OR data works without changes

### Documentation

- **[FLORIDA_QUICKSTART.md](FLORIDA_QUICKSTART.md)** - Quick setup guide
- **[MULTI_REGION_GUIDE.md](MULTI_REGION_GUIDE.md)** - Comprehensive documentation
- **[IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)** - Technical details

### For Developers

To add region support to your scraper:

```python
from app.lowes_stores_fl import LOWES_STORES_FL

# Set region when creating stores
repo.upsert_store(
    session,
    store_id=store_id,
    name=store_name,
    zip_code=zip_code,
    city=city,
    state=state,
    region="FL"  # or "WA_OR"
)

# Set region on observations
observation = Observation(
    # ... other fields ...
    region="FL",  # or "WA_OR"
)
```

### Database Schema

New `region` column added to:
- `stores.region`
- `observations.region`
- `store_price_history.region`

Values: `"WA_OR"`, `"FL"`, or `NULL` (legacy data)
