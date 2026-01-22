import os
import stripe
from dotenv import load_dotenv

load_dotenv()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
TARGET_URL = "https://cheapskater.onrender.com/auth/webhook/stripe"

def setup_webhook():
    print(f"Checking webhooks for: {TARGET_URL}")
    
    if not stripe.api_key:
        print("Error: STRIPE_SECRET_KEY not set in .env")
        return

    try:
        # Check existing endpoints
        endpoints = stripe.WebhookEndpoint.list(limit=10)
        existing = next((ep for ep in endpoints.data if ep.url == TARGET_URL), None)
        
        if existing:
            print(f"\nFound existing webhook: {existing.id}")
            if existing.status != "enabled":
                print("Note: This webhook is disabled.")
            print(f"Secret: {existing.secret}") # This might be hidden in some API versions, but usually available on retrieve/create
            # Actually, retrieve doesn't show secret? 
            # documentation says: "The secret is returned in the response for creation... but NOT for retrieval."
            # That's a problem. If it exists, we might need to roll it or create a new one if we don't have the secret.
            # But the user doesn't have it.
            
            print("Existing secret cannot be retrieved via API for security.")
            print("Creating a NEW webhook to ensure we have the secret...")
            # Ideally we might delete the old one or just make a new one.
            # Let's make a new one to be safe and ensure we have the key.
            # stripe.WebhookEndpoint.delete(existing.id)
            # print("Deleted old webhook.")
            pass

        print("\nCreating new Stripe Webhook...")
        endpoint = stripe.WebhookEndpoint.create(
            url=TARGET_URL,
            enabled_events=[
                "checkout.session.completed",
                "customer.subscription.updated",
                "customer.subscription.deleted",
            ],
            description="Production Webhook for CheapSkater (Auto-generated)",
        )
        print(f"SUCCESS! Webhook created.")
        print(f"ID: {endpoint.id}")
        print(f"Secret: {endpoint.secret}")
        
        # We need to capture this output
        print(f"!!!SET_ENV_VAR:STRIPE_WEBHOOK_SECRET={endpoint.secret}!!!")

    except Exception as e:
        print(f"Error managing webhooks: {e}")

if __name__ == "__main__":
    setup_webhook()
