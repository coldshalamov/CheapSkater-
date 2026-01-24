# 🤖 CheapSkater Frontend Dashboard
### Multi-Region Lowe's Clearance Tracker

**⚠️ This repository contains the FRONTEND SITE ONLY. The scraping functionality is in a separate coordinator/scraper repository.**

CheapSkater is a high-performance, real-time clearance tracking dashboard that displays 50-90% off deals from Lowe's stores across multiple regions (currently Florida and Pacific Northwest). Built with a distinctive "Industrial Treasure Hunter" aesthetic, it transforms clearance data into a premium browsing experience.

---

## 🚀 Key Features

*   **The Treasure Dashboard**: A custom-designed, industrial-themed FastAPI dashboard for browsing, filtering, and saving deals.
*   **Multi-Region Support**: Browse deals from Florida or Pacific Northwest (WA/OR) with region-specific filtering.
*   **Premium Membership (Stripe)**: Integrated subscription system for up-to-the-minute deal access and advanced features.
*   **Targeted Deal Alerts**: Email notification system allowing users to monitor specific categories or keywords.
*   **Real-Time Updates**: Pro users see deals posted instantly as they're discovered.
*   **Smart Search**: Filter by item name, store, or SKU across all listings.
*   **User Authentication**: Secure login, registration, and password reset flows.
*   **Admin Panel**: Comprehensive admin interface for managing deals, users, and system messages.

---

## 🛠 Technology Stack

*   **Backend**: [FastAPI](https://fastapi.tiangolo.com/) (Async Python)
*   **Database**: SQLAlchemy ORM with SQLite (populated by separate scraper service)
*   **Payments**: [Stripe](https://stripe.com/) Checkout & Customer Portal
*   **Email**: [SendGrid](https://sendgrid.com/)
*   **Frontend**: Semantic HTML5, Vanilla CSS (Industrial Theme), Jinja2 Templates
*   **Deployment**: [Render.com](https://render.com/)

---

## 🏁 Quick Start

### 1. Installation
```bash
# Clone the repository
git clone https://github.com/coldshalamov/CheapSkater-
cd CheapSkater-

# Set up virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration
Copy `.env.example` to `.env` and fill in your credentials:
```bash
cp .env.example .env
```
Key Variables:
*   `CHEAPSKATER_DB_PATH`: Path to SQLite database (default: `orwa_lowes.sqlite`)
*   `CHEAPSKATER_SESSION_SECRET`: Random string for secure cookies
*   `STRIPE_SECRET_KEY` / `STRIPE_PUBLISHABLE_KEY`: From your Stripe dashboard
*   `SENDGRID_API_KEY`: For email notifications
*   `ADMIN_USERNAME` / `ADMIN_PASSWORD_HASH`: Admin credentials

### 3. Launching

**Windows:**
```bash
LAUNCH_SITE.bat
```

**Mac/Linux or Manual:**
```bash
python -m uvicorn app.dashboard:app --host 0.0.0.0 --port 9000 --reload
```

Open [http://localhost:9000](http://localhost:9000) to see the dashboard.

**⚠️ DO NOT use the old launchers in `quarantine/legacy_scraper/launchers/` - those are for the deprecated scraper!**

See `HOW_TO_LAUNCH.md` for detailed launch instructions.

---

## 🏗 System Architecture

### Frontend Application (`app/dashboard.py`)
The main FastAPI application that handles:
*   **Public/Member Content**: Restricts real-time deal access based on Stripe subscription status
*   **Regional Views**: Separate routes for Florida (`/`) and Pacific Northwest (`/pnw`)
*   **Search & Filtering**: Advanced filtering by category, discount, stock, price, and keyword search
*   **User Management**: Authentication, registration, password reset

### Authentication (`app/auth/`)
Secure middleware for session management, PBKDF2 password hashing, and Stripe integration for subscription upgrades.

### Admin Panel (`app/admin/`)
Comprehensive admin interface for:
*   Managing deals (delete, edit)
*   Viewing user accounts and activity
*   System messages and scraper heartbeat monitoring

### Notifications (`app/notifications/`)
Email alert system that matches deals against user-defined criteria and sends notifications via SendGrid.

### Database
Reads from `orwa_lowes.sqlite` which is populated by the separate scraper/coordinator service. Contains:
*   `observations` - Raw price observations
*   `store_price_history` - Compressed price history
*   `users` - User accounts and subscriptions
*   `deal_alerts` - User-defined alert rules

---

## 💰 Subscription Model

*   **Free**: Browse deals older than 5 days, basic filtering
*   **Basic ($10/mo)**: See deals from the last 3 days
*   **Pro ($20/mo)**: Up-to-the-minute deal access, advanced filters
*   **Premium ($30/mo)**: All Pro features + priority support

---

## 🛠 Useful Scripts

*   `scripts/purge_old_data.py` - Clean up old database entries
*   `scripts/create_admin.py` - Create admin user
*   `scripts/test_email.py` - Test email configuration

---

## 📚 Documentation

*   `HOW_TO_LAUNCH.md` - Detailed launch instructions
*   `ARCHITECTURE.md` - System architecture overview
*   `AUTH_AND_PAYWALL_GUIDE.md` - Authentication and subscription details
*   `ADMIN_FEATURES.md` - Admin panel documentation
*   `DEPLOYMENT_GUIDE.md` - Render.com deployment instructions
*   `MULTI_REGION_GUIDE.md` - Multi-region setup guide

---

## 📜 Legal & Usage
*This tool is intended for personal research and price monitoring only. Please respect Lowe's robots.txt and usage policies. CheapSkater is not affiliated with, authorized, or endorsed by Lowe's Companies, Inc.*

---

**Happy Hunting!** 🤖💰🏚️
