"""
Database migration script to add region support to CheapSkater.

This script adds the 'region' column to the stores, observations, and store_price_history tables.
It also populates the region field for existing stores based on their state.

Usage:
    python scripts/migrate_add_region.py
"""

import sqlite3
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.storage.db import resolve_database_file

def migrate_database():
    """Add region column to database tables and populate existing data."""
    
    db_path = resolve_database_file(fallback=Path("orwa_lowes.sqlite"))
    print(f"Migrating database: {db_path}")
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Add region column to stores table
        print("Adding region column to stores table...")
        try:
            cursor.execute("ALTER TABLE stores ADD COLUMN region TEXT")
            print("  ✓ Added region column to stores")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("  ℹ Region column already exists in stores")
            else:
                raise
        
        # Add region column to observations table
        print("Adding region column to observations table...")
        try:
            cursor.execute("ALTER TABLE observations ADD COLUMN region TEXT")
            print("  ✓ Added region column to observations")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("  ℹ Region column already exists in observations")
            else:
                raise
        
        # Add region column to store_price_history table
        print("Adding region column to store_price_history table...")
        try:
            cursor.execute("ALTER TABLE store_price_history ADD COLUMN region TEXT")
            print("  ✓ Added region column to store_price_history")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                print("  ℹ Region column already exists in store_price_history")
            else:
                raise
        
        # Populate region for existing stores based on state
        print("\nPopulating region for existing stores...")
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
        print(f"  ✓ Updated {stores_updated} stores")
        
        # Populate region for existing observations
        print("Populating region for existing observations...")
        cursor.execute("""
            UPDATE observations 
            SET region = (
                SELECT stores.region 
                FROM stores 
                WHERE stores.id = observations.store_id
            )
            WHERE region IS NULL
        """)
        obs_updated = cursor.rowcount
        print(f"  ✓ Updated {obs_updated} observations")
        
        # Populate region for existing price history
        print("Populating region for existing price history...")
        cursor.execute("""
            UPDATE store_price_history 
            SET region = (
                SELECT stores.region 
                FROM stores 
                WHERE stores.id = store_price_history.store_id
            )
            WHERE region IS NULL
        """)
        history_updated = cursor.rowcount
        print(f"  ✓ Updated {history_updated} price history records")
        
        # Create index on region column for observations
        print("\nCreating indexes...")
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_observations_region ON observations(region)")
            print("  ✓ Created index on observations.region")
        except sqlite3.OperationalError as e:
            print(f"  ℹ Index may already exist: {e}")
        
        conn.commit()
        print("\n✅ Migration completed successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    migrate_database()
