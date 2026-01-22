import os
import stripe
from dotenv import load_dotenv

load_dotenv()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

def setup_stripe():
    print("Checking Stripe configuration...")
    
    if not stripe.api_key:
        print("Error: STRIPE_SECRET_KEY not set in .env")
        return

    try:
        # Check connection
        account = stripe.Account.retrieve()
        print(f"Connected to Stripe account: {account.id} ({account.email})")
    except Exception as e:
        print(f"Error connecting to Stripe: {e}")
        return

    # Define plans we want
    plans = {
        "basic": {"name": "CheapSkater Basic", "amount": 999},  # $9.99
        "pro": {"name": "CheapSkater Pro Access", "amount": 5000}, # $50.00
        "premium": {"name": "CheapSkater Premium", "amount": 20000}, # $200.00
    }
    
    found_prices = {}

    # List existing products
    print("\nScanning existing products...")
    products = stripe.Product.list(active=True, limit=100)
    
    for plan_key, plan_data in plans.items():
        # Look for existing product
        product = next((p for p in products.data if p.name == plan_data["name"]), None)
        
        if product:
            print(f"Found existing product: {product.name} ({product.id})")
        else:
            print(f"Creating product: {plan_data['name']}...")
            product = stripe.Product.create(name=plan_data["name"])
            
        # Look for price
        prices = stripe.Price.list(product=product.id, active=True, limit=5)
        price = next((p for p in prices.data if p.unit_amount == plan_data["amount"] and p.currency == "usd" and p.recurring), None)
        
        if price:
            print(f"  Found matching price: {price.id} (${price.unit_amount/100})")
        else:
            print(f"  Creating price for {product.name}...")
            price = stripe.Price.create(
                product=product.id,
                unit_amount=plan_data["amount"],
                currency="usd",
                recurring={"interval": "month"},
            )
            print(f"  Created price: {price.id}")
            
        found_prices[plan_key] = price.id

    print("\n--- Configuration for .env ---")
    print(f"STRIPE_PRICE_BASIC={found_prices['basic']}")
    print(f"STRIPE_PRICE_PRO={found_prices['pro']}")
    print(f"STRIPE_PRICE_PREMIUM={found_prices['premium']}")
    print(f"STRIPE_PRICE_ENTERPRISE={found_prices['premium']} # Legacy alias")

if __name__ == "__main__":
    setup_stripe()
