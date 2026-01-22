# Discount Fix Deployment Guide

## What's Being Changed

### 1. **app/ingest.py** (Main Fix)
- ✅ Adds `_calculate_discount_percent()` function
- ✅ Recalculates `pct_off` during ingestion instead of trusting Gloorbot
- ✅ **Safe**: Only affects NEW deals coming in
- ✅ **No data loss**: Doesn't touch existing database entries

### 2. **app/templates/dashboard.html** (UI Improvement)
- ✅ Improves clipboard copy for store names
- ✅ Changes: "Hialeah, FL (#2254)" → "Hialeah, FL 2254" (removes parentheses)
- ✅ **Safe**: Pure UI change, no database impact

### 3. **tests/test_discount_fix.py** (Testing)
- ✅ New test file
- ✅ **Safe**: Only runs during testing, zero production impact

## Deployment Steps

### Step 1: Commit and Push Changes
```bash
# Review changes one more time
git diff

# Add files
git add app/ingest.py app/templates/dashboard.html .gitignore

# Commit
git commit -m "Fix: Recalculate discount percentages for accuracy

- Add _calculate_discount_percent() to ensure accurate % off badges
- Fix clipboard copy to remove parentheses from store names
- Prevents incorrect discounts like '92% off' when actual is ~25%"

# Push to GitHub
git push origin main
```

### Step 2: Deploy to Render
1. Go to your Render dashboard
2. Find your CheapSkater service
3. Click "Manual Deploy" → "Deploy latest commit"
4. Wait for deployment to complete (~2-3 minutes)

### Step 3: Verify New Deals Work
1. Wait for Gloorbot to send new deals
2. Check the dashboard - new deals should have correct % off badges
3. **Old deals will still show incorrect percentages** (this is expected)

### Step 4: Fix Existing Deals (Optional but Recommended)

**Option A: Run locally (if you have the database file)**
```bash
python scripts/fix_existing_discounts.py
```

**Option B: Run on Render (recommended)**
1. SSH into your Render instance or use Render Shell
2. Run:
```bash
cd /opt/render/project/src
python scripts/fix_existing_discounts.py
```

**Option C: Wait for natural refresh**
- As Gloorbot re-scrapes products, they'll automatically get correct percentages
- Takes a few days to fully refresh

## Safety Checklist

- ✅ **No database schema changes** - Only updating values
- ✅ **No data deletion** - Only recalculating pct_off
- ✅ **Backward compatible** - Works with existing Gloorbot format
- ✅ **Tested** - Test suite passes
- ✅ **Reversible** - Can revert Git commit if needed

## What Could Go Wrong?

### Scenario 1: Render deployment fails
- **Fix**: Check Render logs, usually a dependency issue
- **Rollback**: Render keeps previous deployment, click "Rollback"

### Scenario 2: New deals stop appearing
- **Unlikely**: The ingestion logic is unchanged, just adds a calculation
- **Debug**: Check Render logs for errors in `/api/ingest/deals`
- **Rollback**: Revert the Git commit and redeploy

### Scenario 3: Existing deals still show wrong %
- **Expected**: This is normal! Run the migration script (Step 4)
- **Not a bug**: The fix only applies to new ingestions

## Expected Results

### Before Fix
- Closet organizer: **92% OFF** (wrong)
- Actual price: $905.38 from $1,214.50

### After Fix (New Deals)
- Closet organizer: **25% OFF** (correct)
- Calculation: ((1214.50 - 905.38) / 1214.50) × 100 = 25.45%

### After Migration (Old Deals)
- All existing deals recalculated
- Database updated with correct percentages
- No data loss

## Questions?

- **Will this break the site?** No, very low risk
- **Will I lose data?** No, only updating pct_off values
- **Can I rollback?** Yes, via Git revert or Render rollback
- **Do I need to run the migration?** Not required, but recommended for accuracy

## Recommended Approach

1. ✅ Push changes to GitHub (safe)
2. ✅ Deploy to Render (safe, only affects new deals)
3. ✅ Test with a few new deals from Gloorbot
4. ✅ Run migration script to fix existing deals (optional)
5. ✅ Verify everything looks correct

**Total downtime:** ~0 minutes (Render does rolling deployments)
