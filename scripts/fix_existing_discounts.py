"""
Database migration to recalculate pct_off for all existing entries.

This script will:
1. Connect to your database
2. Recalculate pct_off for all rows based on actual price and was_price
3. Update the database with correct values

USAGE:
    python scripts/fix_existing_discounts.py

SAFETY:
    - Only updates pct_off column (doesn't touch prices or other data)
    - Uses a transaction (can be rolled back if something goes wrong)
    - Shows a preview before applying changes
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.storage.db import get_engine, make_session, resolve_database_file
from sqlalchemy import text


def calculate_discount_percent(price: float, was_price: float) -> float:
    """Calculate accurate discount percentage."""
    if was_price <= 0 or price <= 0:
        return 0.0
    if price >= was_price:
        return 0.0
    
    discount = ((was_price - price) / was_price) * 100.0
    return max(0.0, min(100.0, discount))


def main():
    print("=" * 60)
    print("DISCOUNT PERCENTAGE RECALCULATION SCRIPT")
    print("=" * 60)
    
    # Get database connection
    BASE_PATH = Path(__file__).resolve().parent.parent
    FALLBACK_DATABASE_FILE = (BASE_PATH / "orwa_lowes.sqlite").resolve()
    DATABASE_FILE = resolve_database_file(fallback=FALLBACK_DATABASE_FILE)
    
    print(f"\nDatabase: {DATABASE_FILE}")
    
    if not DATABASE_FILE.exists():
        print("❌ Database file not found!")
        return
    
    DB_BUSY_TIMEOUT = float(os.getenv("DB_BUSY_TIMEOUT", "30"))
    engine = get_engine(str(DATABASE_FILE), busy_timeout=DB_BUSY_TIMEOUT)
    session_factory = make_session(engine)
    
    with session_factory() as session:
        # Get all rows with price data
        print("\n📊 Analyzing database...")
        result = session.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN pct_off IS NOT NULL THEN 1 END) as with_pct_off,
                COUNT(CASE WHEN price > 0 AND price_was > 0 THEN 1 END) as calculable
            FROM store_price_history
        """))
        stats = result.fetchone()
        
        print(f"\nTotal rows: {stats.total:,}")
        print(f"Rows with pct_off: {stats.with_pct_off:,}")
        print(f"Rows with calculable prices: {stats.calculable:,}")
        
        # Preview some incorrect values
        print("\n🔍 Sample of potentially incorrect discounts:")
        result = session.execute(text("""
            SELECT 
                title,
                price,
                price_was,
                pct_off,
                ROUND(((price_was - price) / price_was) * 100, 2) as correct_pct_off
            FROM store_price_history
            WHERE price > 0 AND price_was > 0 AND pct_off IS NOT NULL
            AND ABS(pct_off - ((price_was - price) / price_was) * 100) > 5
            LIMIT 5
        """))
        
        print("\n{:<50} {:>10} {:>10} {:>10} {:>10}".format(
            "Title", "Price", "Was", "Current%", "Correct%"
        ))
        print("-" * 90)
        
        samples = result.fetchall()
        for row in samples:
            title = row.title[:47] + "..." if len(row.title) > 50 else row.title
            print("{:<50} ${:>9.2f} ${:>9.2f} {:>9.1f}% {:>9.1f}%".format(
                title, row.price, row.price_was, row.pct_off or 0, row.correct_pct_off or 0
            ))
        
        if not samples:
            print("✅ No incorrect discounts found! All values are already accurate.")
            return
        
        # Ask for confirmation
        print("\n" + "=" * 60)
        response = input("\n⚠️  Apply fix to ALL rows? (yes/no): ").strip().lower()
        
        if response != "yes":
            print("❌ Cancelled. No changes made.")
            return
        
        # Apply the fix
        print("\n🔧 Recalculating discount percentages...")
        
        # Update all rows
        result = session.execute(text("""
            UPDATE store_price_history
            SET pct_off = CASE
                WHEN price_was <= 0 OR price <= 0 THEN 0.0
                WHEN price >= price_was THEN 0.0
                ELSE ROUND(((price_was - price) / price_was) * 100.0, 2)
            END
            WHERE price > 0 AND price_was > 0
        """))
        
        rows_updated = result.rowcount
        session.commit()
        
        print(f"\n✅ Successfully updated {rows_updated:,} rows!")
        
        # Verify the fix
        print("\n🔍 Verifying fix...")
        result = session.execute(text("""
            SELECT 
                COUNT(*) as still_wrong
            FROM store_price_history
            WHERE price > 0 AND price_was > 0 AND pct_off IS NOT NULL
            AND ABS(pct_off - ((price_was - price) / price_was) * 100) > 0.1
        """))
        
        still_wrong = result.fetchone().still_wrong
        
        if still_wrong == 0:
            print("✅ All discount percentages are now accurate!")
        else:
            print(f"⚠️  {still_wrong} rows still have minor discrepancies (likely rounding)")
        
        print("\n" + "=" * 60)
        print("MIGRATION COMPLETE")
        print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
