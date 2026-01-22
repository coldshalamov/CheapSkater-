# Admin Dashboard Features - Implementation Guide

This document describes the comprehensive admin dashboard system that has been added to CheapSkater.

## Overview

The admin dashboard provides real-time monitoring and management capabilities for:
- Scraper health and heartbeat tracking
- Live deal ingestion metrics
- User management and activity tracking
- System-wide messaging
- Store performance analytics

## Architecture

### Database Models (`app/admin/models.py`)

#### ScraperHeartbeat
Tracks active scrapers and their operational status.
- Fields: scraper_id, last_heartbeat, deals_ingested_total, deals_ingested_session, errors_count, version, hostname
- Auto-updated when deals are ingested
- Timeout detection (5 minutes default)

#### SystemMessage
Global messages displayed at the top of all pages.
- Fields: message, message_type (info/warning/error/success), priority, is_active, expires_at
- Supports expiration and priority ordering

#### UserActivity
Tracks all user actions across the platform.
- Fields: user_id, activity_type, ip_address, user_agent, occurred_at
- Activity types: login, logout, page_view, api_call

#### ActiveSession
Tracks currently logged-in users.
- Fields: user_id, session_token, ip_address, last_activity, expires_at
- Enables "who's online" detection

#### IngestionMetrics
Aggregated deal ingestion statistics.
- Time-windowed metrics (5-minute windows)
- Tracks deals_count, unique_stores, unique_skus, avg_discount_pct

### Service Layer (`app/admin/service.py`)

**AdminService** provides all admin operations:

#### Scraper Management
- `update_heartbeat()` - Record scraper activity
- `get_active_scrapers()` - Get scrapers with recent heartbeats
- `get_all_scrapers()` - Get all scraper records
- `mark_scraper_inactive()` - Manually deactivate a scraper

#### System Messages
- `create_system_message()` - Post new system-wide message
- `get_active_system_messages()` - Get messages to display
- `update_system_message()` - Edit existing message
- `delete_system_message()` - Remove message

#### User Activity & Sessions
- `log_activity()` - Record user action
- `get_user_activities()` - Get user's recent activity
- `get_unique_ips_for_user()` - Get all IPs used by user
- `create_or_update_session()` - Manage active sessions
- `get_active_sessions_for_user()` - Check if user is online

#### User Management
- `get_all_users_with_stats()` - Get all users with subscription, spending, and activity data
- Online users are sorted to the top

#### Deal Management
- `delete_deal_by_id()` - Remove specific deal
- `delete_deals_by_sku()` - Bulk remove deals for a SKU

#### Analytics
- `get_store_discount_averages()` - Calculate average discounts per store
- `get_ingestion_rate()` - Calculate deals/minute and deals/hour
- `get_dashboard_metrics()` - Comprehensive metrics for admin panel

### API Routes (`app/admin/routes.py`)

#### Admin Pages (HTML)
- `GET /admin/` - Main admin dashboard
- `GET /admin/users` - User management page
- `GET /admin/user/{user_id}` - Detailed user view

#### Scraper APIs
- `POST /admin/api/heartbeat` - Receive scraper heartbeat (API key required)
- `GET /admin/api/scrapers` - Get all scraper status (admin only)

#### System Message APIs
- `POST /admin/api/system-message` - Create message (admin only)
- `GET /admin/api/system-messages` - Get active messages (public)
- `DELETE /admin/api/system-message/{id}` - Delete message (admin only)

#### Deal Management APIs
- `DELETE /admin/api/deal/{deal_id}` - Delete deal (admin only)
- `DELETE /admin/api/deal/sku/{sku}` - Delete all deals for SKU (admin only)

#### Metrics APIs
- `GET /admin/api/metrics` - Full dashboard metrics (admin only)
- `GET /admin/api/stores/discounts` - Store discount averages (admin only)
- `GET /admin/api/ingestion-rate` - Live ingestion rate (public for status pages)

### Middleware (`app/admin/middleware.py`)

**UserActivityMiddleware** automatically tracks:
- Page views
- Login/logout events
- API calls
- Active session management
- IP addresses (stores unique IPs only to save space)
- User agent strings

Applied globally to all requests for logged-in users.

## Integration Points

### 1. Main Dashboard (`app/dashboard.py`)

Added:
```python
# Import admin router
from app.admin.routes import router as admin_router
app.include_router(admin_router)

# Add activity tracking middleware
from app.admin.middleware import UserActivityMiddleware
app.add_middleware(UserActivityMiddleware, database_file=str(DATABASE_FILE))
```

### 2. Ingest Endpoint (`app/ingest.py`)

Added heartbeat tracking:
```python
# After successful deal ingestion
from app.admin.service import AdminService
admin_service = AdminService(session)
admin_service.update_heartbeat(
    scraper_id=client_id,
    scraper_name=f"Gloorbot-{client_id}",
    deals_count=accepted,
    errors_count=errors,
    version=x_gloorbot_version,
    hostname=x_gloorbot_hostname,
)
```

Accepts new headers:
- `X-Gloorbot-Version`
- `X-Gloorbot-Hostname`

### 3. Auth Routes (`app/auth/routes.py`)

Added last_login tracking:
```python
# On successful login
user.last_login_at = datetime.now(timezone.utc)
db_session.commit()
```

## Gloorbot Integration

### Heartbeat Script (`D:\GitHub\Telomere\Gloorbot\heartbeat_integration.py`)

Drop-in module for Gloorbot scrapers:

```python
from heartbeat_integration import send_heartbeat

# Call periodically from your scraper
send_heartbeat(
    client_id="gloorbot-main",
    deals_count=batch_size,
    errors_count=error_count
)
```

Environment variables needed:
- `CHEAPSKATER_API_URL` - Dashboard URL (default: production Render URL)
- `CHEAPSKATER_INGEST_API_KEY` - Same API key used for /api/ingest/deals

Features:
- Auto-detects hostname
- Includes version tracking
- 5-second timeout
- Graceful failure (won't crash scraper if dashboard is down)

## Admin Dashboard UI

Located at `/admin/` (requires `is_admin=True` on user account)

### Main Dashboard Shows:
1. **Active System Messages** - With ability to create/delete
2. **Key Metrics Cards**:
   - Active scrapers count
   - Deals per hour (live ingestion rate)
   - Total users / online users
   - 24-hour deal count

3. **Active Scrapers Table**:
   - Scraper name and ID
   - Last heartbeat timestamp
   - Deals processed (session and total)
   - Error count
   - Version

4. **Top Discount Stores** (24h):
   - Store name/ID
   - Average discount percentage
   - Deal count
   - Last update time

5. **Quick Actions**:
   - Link to User Management
   - Link to Browse Deals
   - Link to raw API metrics

### User Management Page (`/admin/users`)

Shows all users with:
- Online status indicator
- Subscription plan
- Total spent
- Last activity timestamp
- Active session count
- Unique IP count
- Sample of recent IPs

Online users are sorted to the top automatically.

### User Detail Page (`/admin/user/{user_id}`)

Shows:
- Recent activity log (last 50 actions)
- All unique IP addresses
- Active sessions
- Login history

## Security

### Access Control
- All admin pages require `user.is_admin == True`
- Heartbeat endpoint requires API key (`CHEAPSKATER_INGEST_API_KEY`)
- System message creation/deletion requires admin
- Deal deletion requires admin
- User management requires admin

### Privacy Considerations
- **IP Storage**: Only unique IPs are stored to minimize database bloat
- **User Agent**: Stored for security tracking (detect suspicious logins)
- **Activity Log**: Trimmed to recent entries only (configurable)
- **Session Expiry**: Auto-cleanup of expired sessions

## Database Initialization

All admin tables are created automatically by SQLAlchemy's `Base.metadata.create_all()` on app startup.

No migration needed - tables will be created on first run.

## Metrics API Response Format

`GET /admin/api/metrics` returns:

```json
{
  "ok": true,
  "scrapers": {
    "active_count": 2,
    "total_count": 3,
    "scrapers": [
      {
        "id": "gloorbot-main",
        "name": "Gloorbot-main",
        "last_heartbeat": "2026-01-22T10:30:00Z",
        "deals_total": 15000,
        "deals_session": 500,
        "errors": 3,
        "version": "1.0.0"
      }
    ]
  },
  "ingestion": {
    "last_hour": {
      "time_window_hours": 1,
      "total_deals": 450,
      "unique_stores": 12,
      "unique_skus": 380,
      "deals_per_minute": 7.5,
      "deals_per_hour": 450
    },
    "last_24_hours": {
      "total_deals": 12000,
      "deals_per_hour": 500
    }
  },
  "stores": {
    "top_discounts": [
      {
        "store_id": "1234",
        "store_name": "Seattle, WA (#1234)",
        "avg_discount": 68.5,
        "deal_count": 120,
        "last_updated": "2026-01-22T10:25:00Z"
      }
    ]
  },
  "users": {
    "total": 150,
    "online": 12,
    "subscriptions": {
      "free": 120,
      "pro": 25,
      "premium": 5
    }
  }
}
```

## System Message Display

To display system messages on any page, add to your template:

```python
# In your route handler
from app.admin.service import AdminService
admin_service = AdminService(db_session)
system_messages = admin_service.get_active_system_messages()

# Pass to template
return templates.TemplateResponse("page.html", {
    "system_messages": system_messages,
    ...
})
```

```html
<!-- In your template -->
{% if system_messages %}
<div class="system-messages">
  {% for msg in system_messages %}
  <div class="alert alert-{{ msg.message_type }}">
    {{ msg.message }}
  </div>
  {% endfor %}
</div>
{% endif %}
```

## Deal Timestamp Display

Deals are already timestamped in `StorePriceHistory.updated_at`. To display on cards:

```html
<div class="deal-timestamp">
  Added: {{ format_regional_timestamp(deal.updated_at, region) }}
</div>
```

Use the existing `format_regional_timestamp()` Jinja filter from `app/timezone_utils.py`.

## Admin Actions on Deal Cards

For admins viewing deals, add a delete button:

```html
{% if user and user.is_admin %}
<button onclick="deleteDeal({{ deal.id }})" class="btn-delete">
  🗑️ Delete
</button>
{% endif %}

<script>
async function deleteDeal(dealId) {
  if (!confirm('Delete this deal?')) return;

  const response = await fetch(`/admin/api/deal/${dealId}`, {
    method: 'DELETE'
  });

  if (response.ok) {
    location.reload();
  }
}
</script>
```

## Monitoring & Alerts

### Scraper Health Monitoring
- Scrapers that haven't sent heartbeat in 5 minutes are marked inactive
- Check `GET /admin/api/scrapers` for scraper status
- `active_count` vs `total_count` shows health

### Ingestion Rate Monitoring
- `GET /admin/api/ingestion-rate?hours=1` for current rate
- Compare `deals_per_hour` to baseline
- Alert if drops below threshold

### User Activity Spikes
- Query `UserActivity` for unusual patterns
- Check `get_unique_ips_for_user()` for account sharing

## Environment Variables

Required:
- `CHEAPSKATER_INGEST_API_KEY` - Shared API key for scrapers and admin heartbeats

Optional:
- `CHEAPSKATER_DB_PATH` - Database file path (default: orwa_lowes.sqlite)
- `DB_BUSY_TIMEOUT` - SQLite busy timeout in seconds (default: 30)

## Testing Admin Features

1. **Create admin user**:
```bash
python scripts/create_admin.py
```

2. **Access admin dashboard**:
- Navigate to `/admin/`
- Should see metrics, scrapers, stores

3. **Test heartbeat**:
```bash
cd D:\GitHub\Telomere\Gloorbot
python heartbeat_integration.py
```

4. **Test system message**:
- Post a message via admin dashboard
- Check it appears on other pages

## Future Enhancements

Potential additions:
- Email alerts when scrapers go offline
- Automated performance reports
- User behavior analytics
- Deal quality scoring
- Store coverage heatmaps
- Scraper performance comparison charts
- Real-time dashboard with WebSockets

## Troubleshooting

### Heartbeats not appearing
- Check `CHEAPSKATER_INGEST_API_KEY` is set correctly
- Verify API endpoint URL
- Check scraper logs for errors

### User activity not tracked
- Ensure UserActivityMiddleware is registered
- Check database has `user_activity` table
- Verify user is logged in

### System messages not showing
- Call `get_active_system_messages()` in route
- Pass to template context
- Check `is_active=True` and not expired

### Database locked errors
- Increase `DB_BUSY_TIMEOUT`
- Check for long-running queries
- Verify WAL mode is enabled

## Support

For issues or questions:
- Check logs in `logs/app.log`
- Review metrics at `/admin/api/metrics`
- Verify database schema with SQLite browser
