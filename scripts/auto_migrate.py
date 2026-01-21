#!/usr/bin/env python3
"""
Auto-migration script for Render deployment.
This runs before the server starts to ensure the database schema is up to date.
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.storage.db import resolve_database_file

def column_exists(cursor, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns

def auto_migrate():
    """Automatically apply migrations if needed."""
    
    db_path = resolve_database_file(fallback=Path("orwa_lowes.sqlite"))
    print(f"Checking database schema: {db_path}")
    
    if not db_path.exists():
        print("Database doesn't exist yet - will be created on first run")
        return
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Check if region column exists in stores table
        if not column_exists(cursor, "stores", "region"):
            print("⚠️  Region column missing - running migration...")
            
            # Add region column to stores
            cursor.execute("ALTER TABLE stores ADD COLUMN region TEXT")
            print("  ✓ Added region column to stores")
            
            # Add region column to observations
            try:
                cursor.execute("ALTER TABLE observations ADD COLUMN region TEXT")
                print("  ✓ Added region column to observations")
            except sqlite3.OperationalError:
                print("  ℹ Region column already exists in observations")
            
            # Add region column to store_price_history
            try:
                cursor.execute("ALTER TABLE store_price_history ADD COLUMN region TEXT")
                print("  ✓ Added region column to store_price_history")
            except sqlite3.OperationalError:
                print("  ℹ Region column already exists in store_price_history")
            
            # Populate region for existing stores
            cursor.execute("""
                UPDATE stores 
                SET region = CASE 
                    WHEN state IN ('WA', 'OR') THEN 'WA_OR'
                    WHEN state = 'FL' THEN 'FL'
                    ELSE NULL
                END
                WHERE region IS NULL
            """)
            stores_updated = cursor.rowcount
            print(f"  ✓ Updated {stores_updated} stores with region")
            
            # Create index
            try:
                cursor.execute("CREATE INDEX IF NOT EXISTS ix_observations_region ON observations(region)")
                print("  ✓ Created index on observations.region")
            except sqlite3.OperationalError:
                pass
            
            conn.commit()
            print("✅ Migration completed successfully!")
        else:
            print("✓ Database schema is up to date")
            
    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    auto_migrate()
