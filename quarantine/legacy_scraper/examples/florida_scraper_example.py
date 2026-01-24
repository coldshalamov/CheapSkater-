"""
Example: Configuring a Florida Scraper

This example shows how to modify your scraper to support Florida stores
while maintaining backward compatibility with WA/OR stores.
"""

from datetime import datetime, timezone
from app.storage import repo
from app.storage.models_sql import Observation
from app.lowes_stores_wa_or import LOWES_STORES_WA_OR
from app.lowes_stores_fl import LOWES_STORES_FL

def get_region_from_state(state: str) -> str:
    """Automatically determine region from state abbreviation."""
    if state in ("WA", "OR"):
        return "WA_OR"
    elif state == "FL":
        return "FL"
    else:
        # Default to WA_OR for unknown states
        return "WA_OR"

def get_store_info(store_id: str, state: str = None):
    """
    Get store information from the appropriate registry.
    
    Args:
        store_id: The store ID to look up
        state: Optional state hint to determine which registry to check
    
    Returns:
        Store info dict or None if not found
    """
    # Try to determine which registry to use
    if state == "FL":
        return LOWES_STORES_FL.get(store_id)
    elif state in ("WA", "OR"):
        return LOWES_STORES_WA_OR.get(store_id)
    else:
        # Try both registries
        store_info = LOWES_STORES_WA_OR.get(store_id)
        if not store_info:
            store_info = LOWES_STORES_FL.get(store_id)
        return store_info

def process_store_and_create_observation(
    session,
    store_id: str,
    sku: str,
    title: str,
    category: str,
    price: float,
    price_was: float,
    pct_off: float,
    availability: str,
    product_url: str,
    image_url: str = None,
    clearance: bool = True,
):
    """
    Process a store and create an observation with proper region tagging.
    
    This function:
    1. Looks up store info from the appropriate registry
    2. Creates/updates the store with region
    3. Creates an observation with region
    4. Updates price history with region
    """
    
    # Get store info (this will check both registries)
    store_info = get_store_info(store_id)
    
    if not store_info:
        print(f"Warning: Store {store_id} not found in any registry")
        return None
    
    # Extract store details
    store_name = store_info["name"]
    city = store_info["city"]
    state = store_info["state"]
    zip_code = store_info["zip"]
    
    # Determine region from state
    region = get_region_from_state(state)
    
    print(f"Processing store {store_id} ({store_name}) - Region: {region}")
    
    # Upsert store with region
    repo.upsert_store(
        session,
        store_id=store_id,
        name=store_name,
        zip_code=zip_code,
        city=city,
        state=state,
        region=region,  # Important: Set the region!
    )
    
    # Upsert item
    repo.upsert_item(
        session,
        sku=sku,
        retailer="lowes",
        title=title,
        category=category,
        product_url=product_url,
        image_url=image_url,
    )
    
    # Create observation with region
    observation = Observation(
        ts_utc=datetime.now(timezone.utc),
        retailer="lowes",
        store_id=store_id,
        store_name=store_name,
        zip=zip_code,
        region=region,  # Important: Set the region!
        sku=sku,
        title=title,
        category=category,
        price=price,
        price_was=price_was,
        pct_off=pct_off,
        availability=availability,
        product_url=product_url,
        image_url=image_url,
        clearance=clearance,
    )
    
    repo.insert_observation(session, observation)
    
    # Update price history with region
    repo.update_price_history(
        session,
        retailer="lowes",
        store_id=store_id,
        sku=sku,
        title=title,
        category=category,
        ts_utc=observation.ts_utc,
        price=price,
        price_was=price_was,
        pct_off=pct_off,
        availability=availability,
        product_url=product_url,
        image_url=image_url,
        clearance=clearance,
        region=region,  # Important: Set the region!
    )
    
    session.commit()
    
    return observation

# Example usage
def example_scrape_florida_store():
    """Example of scraping a Florida store."""
    from app.storage.db import get_engine, make_session
    
    engine = get_engine("orwa_lowes.sqlite")
    session_factory = make_session(engine)
    session = session_factory()
    
    try:
        # Example Florida deal
        observation = process_store_and_create_observation(
            session,
            store_id="1234",  # Florida store ID
            sku="123456",
            title="Example Clearance Item",
            category="Building Materials",
            price=19.99,
            price_was=49.99,
            pct_off=0.60,
            availability="In Stock",
            product_url="https://www.lowes.com/pd/Example/123456",
            image_url="https://example.com/image.jpg",
            clearance=True,
        )
        
        print(f"Created observation for Florida store: {observation.store_name}")
        print(f"Region: {observation.region}")
        
    finally:
        session.close()

def example_scrape_wa_or_store():
    """Example of scraping a WA/OR store."""
    from app.storage.db import get_engine, make_session
    
    engine = get_engine("orwa_lowes.sqlite")
    session_factory = make_session(engine)
    session = session_factory()
    
    try:
        # Example WA/OR deal
        observation = process_store_and_create_observation(
            session,
            store_id="0004",  # WA/OR store ID
            sku="789012",
            title="Another Clearance Item",
            category="Tools",
            price=29.99,
            price_was=79.99,
            pct_off=0.625,
            availability="Limited Stock",
            product_url="https://www.lowes.com/pd/Example/789012",
            image_url="https://example.com/image2.jpg",
            clearance=True,
        )
        
        print(f"Created observation for WA/OR store: {observation.store_name}")
        print(f"Region: {observation.region}")
        
    finally:
        session.close()

if __name__ == "__main__":
    print("Example 1: Scraping Florida store")
    print("=" * 50)
    # example_scrape_florida_store()  # Uncomment to run
    
    print("\nExample 2: Scraping WA/OR store")
    print("=" * 50)
    # example_scrape_wa_or_store()  # Uncomment to run
    
    print("\nNote: Uncomment the function calls to actually run the examples")
