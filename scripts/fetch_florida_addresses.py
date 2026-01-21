"""
Script to fetch full addresses for Florida Lowe's stores from their website.

This script scrapes the Lowe's store pages to get complete address information
and updates the lowes_stores_fl.py file with accurate data.

Usage:
    python scripts/fetch_florida_addresses.py
"""

import re
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.lowes_stores_fl import LOWES_STORES_FL

def fetch_store_address(store_id: str, url: str) -> dict:
    """
    Fetch store address from Lowe's website.
    
    Returns dict with: address, city, state, zip
    """
    import requests
    from bs4 import BeautifulSoup
    
    try:
        print(f"Fetching store {store_id}...", end=" ")
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for address in common locations
        # Method 1: Look for structured data (JSON-LD)
        script_tags = soup.find_all('script', type='application/ld+json')
        for script in script_tags:
            try:
                import json
                data = json.loads(script.string)
                if isinstance(data, dict) and 'address' in data:
                    addr = data['address']
                    return {
                        'address': f"{addr.get('streetAddress', '')}, {addr.get('addressLocality', '')}, {addr.get('addressRegion', '')} {addr.get('postalCode', '')}".strip(),
                        'city': addr.get('addressLocality', ''),
                        'state': addr.get('addressRegion', 'FL'),
                        'zip': addr.get('postalCode', ''),
                    }
            except:
                pass
        
        # Method 2: Look for address in meta tags or specific elements
        # This is a fallback - you may need to inspect the actual page structure
        
        print("⚠️  Could not parse address")
        return None
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def update_florida_stores():
    """Fetch and update all Florida store addresses."""
    
    print("Fetching Florida Store Addresses")
    print("=" * 60)
    
    updated_stores = {}
    
    for store_id, store_info in LOWES_STORES_FL.items():
        url = store_info.get('url')
        if not url:
            print(f"Store {store_id}: No URL found, skipping")
            continue
        
        # Fetch address
        address_data = fetch_store_address(store_id, url)
        
        if address_data:
            # Update store info
            updated_info = dict(store_info)
            updated_info['address'] = address_data['address']
            if address_data['city']:
                updated_info['city'] = address_data['city']
            if address_data['zip']:
                updated_info['zip'] = address_data['zip']
            
            updated_stores[store_id] = updated_info
            print(f"✓ {address_data['address']}")
        else:
            # Keep original data
            updated_stores[store_id] = store_info
    
    # Generate updated Python code
    print("\n" + "=" * 60)
    print("Generating updated lowes_stores_fl.py...")
    
    lines = ['"""Canonical list of Lowe\'s store metadata for Florida (Stuart to Miami region)."""\n\n']
    lines.append("from __future__ import annotations\n\n")
    lines.append("LOWES_STORES_FL: dict[str, dict[str, str]] = {\n")
    
    current_county = None
    for store_id, info in updated_stores.items():
        # Add county headers (you may need to adjust these)
        city = info['city']
        if city in ['Stuart']:
            county = "MARTIN COUNTY"
        elif city in ['West Palm Beach', 'Lake Park', 'Royal Palm Beach', 'Boynton Beach', 'Boca Raton']:
            county = "PALM BEACH COUNTY"
        elif city in ['Pompano Beach', 'Coral Springs', 'Oakland Park', 'Sunrise', 'Pembroke Pines', 'Southwest Ranches', 'Davie']:
            county = "BROWARD COUNTY"
        else:
            county = "MIAMI-DADE COUNTY"
        
        if county != current_county:
            lines.append(f"    # --- {county} ---\n")
            current_county = county
        
        lines.append(f'    "{store_id}": {{\n')
        lines.append(f'        "name": "{info["name"]}",\n')
        lines.append(f'        "address": "{info["address"]}",\n')
        lines.append(f'        "city": "{info["city"]}",\n')
        lines.append(f'        "state": "{info["state"]}",\n')
        lines.append(f'        "zip": "{info["zip"]}",\n')
        if 'url' in info:
            lines.append(f'        "url": "{info["url"]}",\n')
        lines.append('    },\n')
    
    lines.append("}\n")
    
    # Write to file
    output_path = Path(__file__).parent.parent / "app" / "lowes_stores_fl.py"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print(f"✅ Updated {len(updated_stores)} stores in {output_path}")

if __name__ == "__main__":
    print("Note: This script requires 'requests' and 'beautifulsoup4' packages")
    print("Install with: pip install requests beautifulsoup4\n")
    
    try:
        import requests
        import bs4
    except ImportError:
        print("❌ Missing required packages. Install with:")
        print("   pip install requests beautifulsoup4")
        sys.exit(1)
    
    update_florida_stores()
