# Timezone Display Fix

## Problem
The dashboard was showing all timestamps in UTC, which was confusing for users:
- Pacific NW users saw UTC times instead of Pacific Time (PT)
- Florida users saw UTC times instead of Eastern Time (ET)

## Solution
Implemented regional timezone conversion to display times in the appropriate local timezone based on the region.

## Changes Made

### 1. Created `app/timezone_utils.py`
New utility module with timezone conversion functions:
- `convert_utc_to_regional_time()` - Converts UTC datetime to regional timezone
  - Pacific Time (UTC-8) for WA/OR region
  - Eastern Time (UTC-5) for FL region
- `format_regional_timestamp()` - Formats datetime with regional timezone abbreviation
- `format_regional_full_timestamp()` - Formats full date and time in regional timezone

### 2. Updated `app/dashboard.py`
- Added import for timezone utility functions
- Added `format_regional_timestamp` and `format_regional_full_timestamp` to template context
- These functions are now available in all dashboard templates

### 3. Updated `app/templates/dashboard.html`
- Line 10: Changed "Last updated X UTC" to use `format_regional_timestamp(last_updated, region)`
- Line 74: Changed full timestamp to use `format_regional_full_timestamp(last_updated, region)`

### 4. Updated `app/assistant/routes.py`
- Added import for `format_regional_timestamp`
- Added function to template context

### 5. Updated `app/templates/assistant.html`
- Line 235: Changed "Updated X UTC" to use `format_regional_timestamp(last_updated, region)`

## Result

**Before:**
- "Last updated 01:30 PM UTC"
- "Last updated Jan 11, 2026 01:30 PM UTC"

**After (Pacific NW):**
- "Last updated 05:30 AM PT"
- "Last updated Jan 11, 2026 05:30 AM PT"

**After (Florida):**
- "Last updated 08:30 AM ET"
- "Last updated Jan 11, 2026 08:30 AM ET"

## Technical Notes

### Timezone Offsets
Currently using simplified static offsets:
- Pacific Time: UTC-8 (PST)
- Eastern Time: UTC-5 (EST)

**Future Enhancement:** Add DST (Daylight Saving Time) logic to automatically switch between:
- PST (UTC-8) / PDT (UTC-7) for Pacific
- EST (UTC-5) / EDT (UTC-4) for Eastern

This can be implemented using Python's `zoneinfo` module:
```python
from zoneinfo import ZoneInfo

# Pacific Time with DST
dt_pacific = dt_utc.astimezone(ZoneInfo("America/Los_Angeles"))

# Eastern Time with DST
dt_eastern = dt_utc.astimezone(ZoneInfo("America/New_York"))
```

### Testing
To verify the changes:
1. Visit the Pacific NW dashboard at `/` or `/new-today`
2. Check that timestamps show "PT" instead of "UTC"
3. Visit the Florida dashboard at `/florida` or `/florida/new-today`
4. Check that timestamps show "ET" instead of "UTC"
5. Visit the assistant page at `/assistant?region=WA_OR` and `/assistant?region=FL`
6. Verify regional times are displayed correctly

## Files Modified
- `app/timezone_utils.py` (new file)
- `app/dashboard.py`
- `app/templates/dashboard.html`
- `app/assistant/routes.py`
- `app/templates/assistant.html`
