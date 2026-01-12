"""Storage backends for persisting scraped data."""

# Import all models so they're registered with SQLAlchemy Base
from app.storage.models_sql import (
    Base,
    Store,
    Item,
    Observation,
    Alert,
    Quarantine,
    StorePriceHistory,
)

# Import auth models to ensure they're created with the main schema
try:
    from app.auth.models import User, Subscription, PaymentHistory
except ImportError:
    # Auth module may not be installed in all environments
    pass

# Import notification models for deal alerts
try:
    from app.notifications.models import DealAlert, NotificationLog
except ImportError:
    pass


