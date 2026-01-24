# Dashboard Search & Database Purge Implementation

## Summary

This document summarizes the implementation of search functionality for the dashboard and the database purge command.

## Features Implemented

### 1. Search Functionality

**Backend Changes (`app/dashboard.py`):**
- Added `search_query` parameter to `_apply_filters()` function
- Implemented keyword search across:
  - Item title
  - SKU
  - Store name
  - Store label
- Search is case-insensitive and uses substring matching
- Added `search` parameter to `_normalize_filters()` function
- Added `search` query parameter to all dashboard routes:
  - `/` (Florida dashboard)
  - `/pnw` (Pacific Northwest dashboard)
  - `/new-today` (Florida new items)
  - `/pnw/new-today` (PNW new items)

**Frontend Changes (`app/templates/dashboard.html`):**
- Updated search input placeholder from "SKU, store, etc..." to "Item, Store, SKU, etc..."
- Added `name="search"` attribute to search input for form submission
- Wired search field to preserve value from URL query parameters
- Added sorting notice banner:
  - Blue informational banner stating "Newest items are shown first"
  - For Pro users, adds: "As a Pro member, up-to-the-minute results are posted instantly to the top of the page"

### 2. Database Purge Command

**New Script (`scripts/purge_old_data.py`):**
- Command-line utility to purge old clearance data
- Removes `Observation` and `StorePriceHistory` records older than specified days
- Features:
  - `--days N`: Delete data older than N days (required)
  - `--dry-run`: Preview what would be deleted without actually deleting
  - Interactive confirmation before deletion
  - Detailed logging of deletion counts
  - Automatic VACUUM after deletion to reclaim disk space

**Usage Examples:**
```bash
# Preview what would be deleted (older than 7 days)
python scripts/purge_old_data.py --days 7 --dry-run

# Actually delete data older than 7 days
python scripts/purge_old_data.py --days 7

# Delete data older than 1 day
python scripts/purge_old_data.py --days 1

# Delete data older than 3 days
python scripts/purge_old_data.py --days 3
```

## How Search Works

1. User enters a search term in the search field
2. On form submission, the search term is sent as a query parameter
3. Backend filters listings where the search term appears in:
   - Item title (e.g., "drill", "paint")
   - Store name (e.g., "Olympia", "Tacoma")
   - SKU (e.g., "1000842612")
4. Search is case-insensitive and matches partial strings
5. Results are displayed with all other active filters applied

## Category Display Issues

The user mentioned "weird categories" that don't match actual Lowe's departments. The purge command can help clean up old/bad data that may be causing this issue.

**Recommended Actions:**
1. Run purge command with `--dry-run` to see how much old data exists
2. Purge data older than 7-14 days to remove stale category information
3. Monitor category display after purge to see if issues are resolved
4. If issues persist, investigate category extraction logic in scraper

## Testing Checklist

- [ ] Search by item name (e.g., "drill")
- [ ] Search by store name (e.g., "Olympia")
- [ ] Search by SKU
- [ ] Verify search works on all dashboard pages (/, /pnw, /new-today, /pnw/new-today)
- [ ] Verify search persists in URL and input field after submission
- [ ] Verify sorting notice appears for all users
- [ ] Verify Pro users see additional message about instant updates
- [ ] Test purge command with --dry-run
- [ ] Test actual purge with small retention period (e.g., 30 days)
- [ ] Verify VACUUM runs successfully after purge

## Notes

- Search is performed server-side, not client-side
- Search applies to all listings before grouping by SKU
- The purge command requires user confirmation before deleting data
- Database is automatically optimized (VACUUM) after purge
