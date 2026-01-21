"""
Helper script to generate Florida store entries for lowes_stores_fl.py

This script can help you populate the Florida stores registry by:
1. Manually entering store data
2. Importing from a CSV file
3. Using the Google Maps scraper (if available)

Usage:
    # Interactive mode
    python scripts/populate_florida_stores.py

    # Import from CSV
    python scripts/populate_florida_stores.py --csv florida_stores.csv

CSV Format:
    store_id,name,address,city,state,zip
    1234,LOWE'S OF MIAMI FL,123 Main St,Miami,FL,33101
"""

import argparse
import csv
import sys
from pathlib import Path

def format_store_entry(store_id: str, name: str, address: str, city: str, state: str, zip_code: str) -> str:
    """Format a store entry as Python code."""
    return f'''    "{store_id}": {{
        "name": "{name}",
        "address": "{address}",
        "city": "{city}",
        "state": "{state}",
        "zip": "{zip_code}",
    }},'''

def interactive_mode():
    """Interactively add stores."""
    print("Florida Store Entry (Interactive Mode)")
    print("=" * 50)
    print("Enter store information (or press Ctrl+C to quit)")
    print()
    
    stores = []
    
    while True:
        try:
            print("\nEnter store details:")
            store_id = input("  Store ID (e.g., 1234): ").strip()
            if not store_id:
                break
            
            name = input("  Name (e.g., LOWE'S OF MIAMI, FL): ").strip()
            address = input("  Address (e.g., 123 Main St, Miami, FL 33101): ").strip()
            city = input("  City: ").strip()
            state = input("  State (FL): ").strip() or "FL"
            zip_code = input("  ZIP: ").strip()
            
            stores.append({
                "store_id": store_id,
                "name": name,
                "address": address,
                "city": city,
                "state": state,
                "zip": zip_code,
            })
            
            print(f"  ✓ Added store {store_id}")
            
        except KeyboardInterrupt:
            print("\n\nFinished entering stores.")
            break
    
    return stores

def import_from_csv(csv_path: str):
    """Import stores from a CSV file."""
    stores = []
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            stores.append({
                "store_id": row.get("store_id", "").strip(),
                "name": row.get("name", "").strip(),
                "address": row.get("address", "").strip(),
                "city": row.get("city", "").strip(),
                "state": row.get("state", "FL").strip(),
                "zip": row.get("zip", "").strip(),
            })
    
    print(f"Imported {len(stores)} stores from {csv_path}")
    return stores

def generate_python_code(stores: list[dict]) -> str:
    """Generate Python code for the stores dictionary."""
    if not stores:
        return ""
    
    lines = ['"""Canonical list of Lowe\'s store metadata for Florida."""\n']
    lines.append("from __future__ import annotations\n\n")
    lines.append("LOWES_STORES_FL: dict[str, dict[str, str]] = {\n")
    
    for store in stores:
        lines.append(format_store_entry(
            store["store_id"],
            store["name"],
            store["address"],
            store["city"],
            store["state"],
            store["zip"]
        ))
        lines.append("\n")
    
    lines.append("}\n")
    
    return "".join(lines)

def main():
    parser = argparse.ArgumentParser(description="Populate Florida stores registry")
    parser.add_argument("--csv", help="Import stores from CSV file")
    parser.add_argument("--output", default="app/lowes_stores_fl.py", help="Output file path")
    
    args = parser.parse_args()
    
    # Get stores
    if args.csv:
        stores = import_from_csv(args.csv)
    else:
        stores = interactive_mode()
    
    if not stores:
        print("No stores to add.")
        return
    
    # Generate Python code
    code = generate_python_code(stores)
    
    # Write to file
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(code)
    
    print(f"\n✅ Wrote {len(stores)} stores to {output_path}")
    print("\nGenerated code preview:")
    print("-" * 50)
    print(code[:500] + "..." if len(code) > 500 else code)

if __name__ == "__main__":
    main()
