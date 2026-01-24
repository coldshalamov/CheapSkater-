# Paywall Fix - Free Tier Restrictions

## Summary

Fixed two critical paywall issues:
1. **Paywall bypass on "New Today" pages** - Free users could see all new deals by clicking "New Today"
2. **Changed free tier restriction** from 5 days to 3 days

## Changes Made

### 1. Backend Logic (`app/dashboard.py`)

**File**: `app/dashboard.py`  
**Function**: `_select_items()` (lines 1459-1490)

**Before**:
```python
if scope == "new":
    # New items are always accessible - BUG!
    return repo.get_new_clearance_today(...)

if is_paid:
    return repo.get_clearance_items(...)

# Free tier sees older deals (5 days)
return repo.get_older_clearance_items(..., min_days_old=5)
```

**After**:
```python
# Pro/Paid users see everything
if is_paid:
    if scope == "new":
        return repo.get_new_clearance_today(...)
    return repo.get_clearance_items(...)

# Free tier sees only older deals (3+ days old)
# This applies to BOTH main page and "new today" page
return repo.get_older_clearance_items(..., min_days_old=3)
```

**Impact**:
- ✅ Free users now see only 3+ day old deals on ALL pages
- ✅ "New Today" button no longer bypasses paywall
- ✅ Pro users still see all deals including new ones

### 2. Frontend Text Updates

Updated all user-facing text to reflect 3-day restriction:

**Files Updated**:
1. `app/templates/auth/pricing.html` (3 locations):
   - Free tier feature: "View deals 3+ days old"
   - Promo banner: "free users wait 3 days"
   - Why upgrade section: "Free users only see deals that are 3+ days old"

2. `app/templates/auth/account.html` (1 location):
   - Free tier description: "Free users can only see deals that are 3+ days old"

## Testing

### Test Cases

1. **Free User - Main Page (`/`)**:
   - Should only see deals 3+ days old
   - ✅ Fixed

2. **Free User - New Today (`/new-today`)**:
   - Should only see deals 3+ days old (NOT all new deals)
   - ✅ Fixed - was showing all deals before

3. **Free User - PNW New Today (`/pnw/new-today`)**:
   - Should only see deals 3+ days old
   - ✅ Fixed - was showing all deals before

4. **Pro User - All Pages**:
   - Should see ALL deals including brand new ones
   - ✅ Still works

### How to Test

1. **As Free User**:
   ```
   - Go to http://localhost:9000/
   - Click "New Today" button
   - Verify you only see deals from 3+ days ago
   - Check deal timestamps
   ```

2. **As Pro User**:
   ```
   - Subscribe to Pro plan
   - Go to http://localhost:9000/new-today
   - Verify you see today's deals
   ```

## Impact

- **Security**: Closed paywall bypass vulnerability
- **Revenue**: Free users must upgrade to see fresh deals
- **UX**: Consistent 3-day restriction across all pages
- **Clarity**: All text now accurately reflects 3-day limit

## Files Modified

1. ✅ `app/dashboard.py` - Fixed `_select_items()` logic
2. ✅ `app/templates/auth/pricing.html` - Updated 3 text references
3. ✅ `app/templates/auth/account.html` - Updated 1 text reference

## Status

✅ **Ready to deploy** (when you're ready)

**Note**: Changes are committed locally but NOT pushed to GitHub yet, as requested.
