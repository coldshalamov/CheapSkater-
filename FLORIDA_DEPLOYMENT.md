# Florida Deployment Guide

## Your Florida Setup (Stuart to Miami)

You now have **18 Florida Lowe's stores** configured and ready to scrape:

### Store Coverage
- **Martin County**: 1 store (Stuart)
- **Palm Beach County**: 5 stores (West Palm Beach, Lake Park, Royal Palm Beach, Boynton Beach, Boca Raton)
- **Broward County**: 7 stores (Pompano Beach, Coral Springs, Oakland Park, Sunrise, Pembroke Pines, Southwest Ranches, Davie)
- **Miami-Dade County**: 5 stores (2x Hialeah, North Miami Beach, Miami/Kendall, Homestead)

## Quick Start

### 1. Your Database is Ready ✅
The migration has already been run successfully:
- ✅ Region columns added
- ✅ Existing WA/OR data tagged with `region="WA_OR"`
- ✅ Indexes created

### 2. Florida Stores are Configured ✅
File: `app/lowes_stores_fl.py`
- ✅ All 18 stores from Stuart to Miami
- ✅ Store IDs, names, cities, and ZIP codes
- ✅ Ready to use

### 3. Run the Florida Scraper

You have two options:

#### Option A: Run Florida scraper separately
```bash
# Use the Florida-specific config
python -m app.main --config config_florida.yml --once
```

#### Option B: Modify your existing scraper
Update your scraper code to detect Florida stores and set `region="FL"`:

```python
from app.lowes_stores_fl import LOWES_STORES_FL

# In your scraper, when processing a store:
if store_id in LOWES_STORES_FL:
    region = "FL"
else:
    region = "WA_OR"

# Then use region when creating stores/observations
repo.upsert_store(session, ..., region=region)
```

### 4. View Florida Deals in the UI

1. Start the dashboard:
   ```bash
   python -m app.main --dashboard
   ```

2. Open http://localhost:8000

3. Use the **Region** dropdown to select "Florida"

4. Browse Florida-specific clearance deals!

## Scraper Integration

### Automatic Region Detection

Use this helper function in your scraper:

```python
from app.lowes_stores_wa_or import LOWES_STORES_WA_OR
from app.lowes_stores_fl import LOWES_STORES_FL

def get_store_region(store_id: str) -> str:
    """Automatically determine region from store ID."""
    if store_id in LOWES_STORES_FL:
        return "FL"
    elif store_id in LOWES_STORES_WA_OR:
        return "WA_OR"
    else:
        # Default to WA_OR for unknown stores
        return "WA_OR"
```

### Example Scraper Modification

```python
# When processing each store
for store_id in discovered_stores:
    # Get region
    region = get_store_region(store_id)
    
    # Get store info from appropriate registry
    if region == "FL":
        store_info = LOWES_STORES_FL.get(store_id)
    else:
        store_info = LOWES_STORES_WA_OR.get(store_id)
    
    # Create/update store with region
    repo.upsert_store(
        session,
        store_id=store_id,
        name=store_info["name"],
        zip_code=store_info["zip"],
        city=store_info["city"],
        state=store_info["state"],
        region=region,  # Important!
    )
    
    # Create observations with region
    observation = Observation(
        # ... other fields ...
        region=region,  # Important!
    )
```

## Testing Your Setup

### 1. Test the Florida Store Registry
```bash
python -c "from app.lowes_stores_fl import LOWES_STORES_FL; print(f'Loaded {len(LOWES_STORES_FL)} Florida stores')"
```

Expected output: `Loaded 18 Florida stores`

### 2. Test a Single Florida Store
```bash
# Run scraper for just one FL ZIP code
python -m app.main --zip 33186 --once
```

This will scrape the Miami (Kendall) store.

### 3. Verify in Database
```bash
python -c "
from app.storage.db import get_engine, make_session
from app.storage import repo

engine = get_engine('orwa_lowes.sqlite')
session = make_session(engine)()

# Check for FL stores
from sqlalchemy import select, func
from app.storage.models_sql import Store

count = session.scalar(select(func.count()).select_from(Store).where(Store.region == 'FL'))
print(f'Florida stores in database: {count}')
session.close()
"
```

### 4. View in UI
1. Start dashboard: `python -m app.main --dashboard`
2. Open http://localhost:8000
3. Select "Florida" from Region dropdown
4. You should see Florida deals (if any have been scraped)

## Running Both Regions

### Option 1: Separate Scraper Instances
Run two separate scraper processes:

```bash
# Terminal 1: WA/OR scraper
python -m app.main --config config.yml

# Terminal 2: FL scraper  
python -m app.main --config config_florida.yml
```

### Option 2: Combined ZIP List
Add all ZIPs to one config:

```yaml
retailers:
  lowes:
    zips:
      # WA/OR ZIPs
      - "98101"
      - "97204"
      # ... etc
      # FL ZIPs
      - "33186"
      - "33033"
      # ... etc
```

Then ensure your scraper sets the correct region based on store ID.

## Monitoring

### Check Region Distribution
```bash
python -c "
from app.storage.db import get_engine, make_session
from sqlalchemy import select, func
from app.storage.models_sql import Observation

engine = get_engine('orwa_lowes.sqlite')
session = make_session(engine)()

# Count observations by region
from sqlalchemy import select, func
result = session.execute(
    select(Observation.region, func.count())
    .group_by(Observation.region)
).all()

for region, count in result:
    print(f'{region or \"NULL\"}: {count} observations')

session.close()
"
```

## Troubleshooting

### Florida stores not appearing in UI
1. Check that stores have `region="FL"` in database
2. Verify observations have `region="FL"` 
3. Select "Florida" in the Region dropdown

### Scraper not setting region
1. Make sure you're using the updated `repo.upsert_store()` with `region` parameter
2. Check that your scraper code includes region detection logic
3. Verify `LOWES_STORES_FL` is imported correctly

### Mixed regions showing up
1. Check the Region filter is set correctly
2. Verify database has proper region tags
3. Run migration script again if needed

## Next Steps

1. **Test with one store**: Run a single FL ZIP to verify everything works
2. **Full scrape**: Run the complete Florida scraper
3. **Monitor results**: Check the dashboard for Florida deals
4. **Set up scheduling**: Use the schedule config to run automatically

## Files Reference

- **Store Registry**: `app/lowes_stores_fl.py` (18 stores)
- **Configuration**: `config_florida.yml` (18 ZIP codes)
- **Migration**: `scripts/migrate_add_region.py` (already run ✅)
- **Example Code**: `examples/florida_scraper_example.py`
- **Documentation**: `MULTI_REGION_GUIDE.md`

You're all set! 🎉 Start scraping Florida stores and see those deals in the dashboard!
