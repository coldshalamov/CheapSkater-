# Multi-Region Support for CheapSkater

This document explains how to use the new multi-region feature in CheapSkater, which allows you to track clearance deals from both Washington/Oregon and Florida Lowe's stores.

## Overview

CheapSkater now supports multiple regions:
- **WA_OR**: Washington and Oregon stores (original functionality)
- **FL**: Florida stores (new)

The database and UI have been updated to keep these regions separate while using the same infrastructure.

## Database Changes

### New Fields
Three tables now include a `region` field:
- `stores.region` - The region this store belongs to ('WA_OR' or 'FL')
- `observations.region` - The region for each price observation
- `store_price_history.region` - The region for each price history record

### Migration
To add region support to an existing database:

```bash
python scripts/migrate_add_region.py
```

This script will:
1. Add the `region` column to all relevant tables
2. Populate existing WA/OR stores with region='WA_OR'
3. Create necessary indexes for efficient filtering

## Adding Florida Stores

### 1. Populate the Florida Store Registry

Edit `app/lowes_stores_fl.py` and add Florida store information:

```python
LOWES_STORES_FL: dict[str, dict[str, str]] = {
    "1234": {
        "name": "LOWE'S OF MIAMI, FL",
        "address": "123 Main St, Miami, FL 33101",
        "city": "Miami",
        "state": "FL",
        "zip": "33101",
    },
    # Add more Florida stores...
}
```

### 2. Update Configuration

In your scraper configuration, you can add Florida ZIP codes to scrape:

```yaml
retailers:
  lowes:
    enabled: true
    zips:
      # Washington/Oregon ZIPs
      - "98101"
      - "97204"
      # Florida ZIPs
      - "33101"
      - "33139"
      # etc...
```

### 3. Configure Scraper to Set Region

When ingesting data, ensure the scraper sets the `region` parameter:

```python
# For WA/OR stores
repo.upsert_store(
    session,
    store_id="0004",
    name="LOWE'S OF RAINIER, WA",
    zip_code="98144",
    city="Seattle",
    state="WA",
    region="WA_OR"
)

# For FL stores
repo.upsert_store(
    session,
    store_id="1234",
    name="LOWE'S OF MIAMI, FL",
    zip_code="33101",
    city="Miami",
    state="FL",
    region="FL"
)
```

## Using the UI

### Separate Pages

The application is now divided into two main sections:

1.  **Pacific Northwest (WA & OR)**: Accessible at the root URL (`/`)
2.  **Florida**: Accessible at `/florida`

Use the top navigation bar to switch between regions.

### State Filter

- **Pacific NW Page**: Includes a State dropdown to filter between WA and OR.
- **Florida Page**: Shows all Florida stores (state filter is hidden).

### Filtering Behavior

- When you select a region, only stores from that region are shown
- The state filter works within the selected region
- All other filters (category, discount, etc.) work the same way

## API Changes
### Routes

- `GET /` - Pacific NW (WA/OR) Dashboard
- `GET /new-today` - Pacific NW New Items
- `GET /florida` - Florida Dashboard
- `GET /florida/new-today` - Florida New Items

### Query Parameters

Dashboard endpoints still use `region` internally, but it depends on the route:
- Root routes default to `region=WA_OR`
- Florida routes force `region=FL`

### Repository Functions

Repository functions now accept an optional `region` parameter:

```python
# Get clearance items for Florida only
items = repo.get_clearance_items(session, region="FL")

# Get new clearance for WA/OR
items = repo.get_new_clearance_today(session, region="WA_OR")

# Get categories for a specific region
categories = repo.list_distinct_categories(session, region="FL")
```

## Scraper Integration

### Setting Region on Observations

When creating observations, set the region:

```python
observation = Observation(
    ts_utc=datetime.now(timezone.utc),
    retailer="lowes",
    store_id=store_id,
    store_name=store_name,
    zip=zip_code,
    region="FL",  # or "WA_OR"
    sku=sku,
    title=title,
    category=category,
    price=price,
    # ... other fields
)
```

### Updating Price History

The `update_price_history` function now accepts a `region` parameter:

```python
repo.update_price_history(
    session,
    retailer="lowes",
    store_id=store_id,
    sku=sku,
    title=title,
    category=category,
    ts_utc=datetime.now(timezone.utc),
    price=price,
    price_was=price_was,
    pct_off=pct_off,
    availability=availability,
    product_url=product_url,
    image_url=image_url,
    clearance=True,
    region="FL"  # or "WA_OR"
)
```

## Reconfiguring the Scraper for Florida

To create a Florida-specific scraper instance:

1. **Create a Florida configuration file** (`config_florida.yml`):
```yaml
retailers:
  lowes:
    enabled: true
    zips:
      - "33101"  # Miami
      - "33139"  # Miami Beach
      - "33301"  # Fort Lauderdale
      # Add more FL ZIPs
    catalog_path: "catalog/building_materials.lowes.yml"
output:
  sqlite_path: "orwa_lowes.sqlite"  # Same database
schedule:
  minutes: 180
```

2. **Run the scraper with the Florida config**:
```bash
python -m app.main --config config_florida.yml
```

3. **Ensure the scraper sets `region="FL"`** when creating stores and observations

## Best Practices

1. **Keep regions separate in the scraper**: Run separate scraper instances for WA/OR and FL to avoid confusion
2. **Always set the region field**: When creating stores, observations, or price history records
3. **Use the region filter in the UI**: To focus on deals relevant to your location
4. **Populate store registries**: Keep `lowes_stores_wa_or.py` and `lowes_stores_fl.py` up to date for accurate store information

## Troubleshooting

### Existing data not showing region
Run the migration script:
```bash
python scripts/migrate_add_region.py
```

### Florida stores not appearing
1. Check that stores have `region="FL"` set
2. Verify observations have `region="FL"` set
3. Ensure the Florida store registry (`lowes_stores_fl.py`) is populated

### Region filter not working
1. Check that the database has been migrated
2. Verify that data has the region field populated
3. Check browser console for JavaScript errors

## Future Enhancements

Potential improvements for multi-region support:
- Automatic region detection based on ZIP code
- Region-specific scraper configurations
- Region comparison views
- Per-region analytics and trends
