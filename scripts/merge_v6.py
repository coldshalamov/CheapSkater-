
import sqlite3
import sys
import os
from pathlib import Path

def merge_databases(source_path: str, dest_path: str):
    if not os.path.exists(source_path):
        print(f"Error: Source database '{source_path}' not found.")
        return
    
    if not os.path.exists(dest_path):
        print(f"Destination database '{dest_path}' not found. Copying source to dest as a starting point...")
        import shutil
        shutil.copy2(source_path, dest_path)
        print("Done.")
        return

    print(f"Merging '{source_path}' into '{dest_path}'...")
    
    # Connect to destination
    conn = sqlite3.connect(dest_path)
    cursor = conn.cursor()
    
    # Attach source
    cursor.execute("ATTACH DATABASE ? AS source", (source_path,))
    
    try:
        # Merge Stores
        print("Merging Stores...")
        cursor.execute("""
        INSERT OR IGNORE INTO stores (id, name, city, state, zip, region)
        SELECT id, name, city, state, zip, region FROM source.stores
        """)
        print(f"  Merged {cursor.rowcount} stores.")
        
        # Merge Items
        print("Merging Items...")
        cursor.execute("""
        INSERT OR IGNORE INTO items (sku, retailer, title, category, product_url, image_url)
        SELECT sku, retailer, title, category, product_url, image_url FROM source.items
        """)
        print(f"  Merged {cursor.rowcount} items.")

        # Merge Observations
        print("Merging Observations...")
        # Since 'id' is autoincrement, we might want to preserve it or let it regenerate.
        # Preserving it is safer for history if we are merging "old" into "new".
        cursor.execute("""
        INSERT OR IGNORE INTO observations (id, ts_utc, retailer, store_id, store_name, zip, region, sku, title, category, price, price_was, pct_off, availability, product_url, image_url, clearance)
        SELECT id, ts_utc, retailer, store_id, store_name, zip, region, sku, title, category, price, price_was, pct_off, availability, product_url, image_url, clearance FROM source.observations
        """)
        print(f"  Merged {cursor.rowcount} observations.")

        # Merge Store Price History
        print("Merging Price History...")
        cursor.execute("""
        INSERT OR IGNORE INTO store_price_history (id, retailer, store_id, region, sku, title, category, started_at, updated_at, price, price_was, pct_off, availability, product_url, image_url, clearance)
        SELECT id, retailer, store_id, region, sku, title, category, started_at, updated_at, price, price_was, pct_off, availability, product_url, image_url, clearance FROM source.store_price_history
        """)
        print(f"  Merged {cursor.rowcount} history records.")

        conn.commit()
        print("Merge complete.")
        
    except Exception as e:
        print(f"Error during merge: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python merge_v6.py <source_db> <dest_db>")
        sys.exit(1)
    
    merge_databases(sys.argv[1], sys.argv[2])
