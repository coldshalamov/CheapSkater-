# 🤖 GloorBot: Industrial Treasure Hunter
### WA & OR Lowe's Clearance Tracker

GloorBot is a high-performance, real-time clearance tracking system designed to hunt down 50-90% off deals at every Lowe's store across Washington and Oregon. Built with a distinctive "Industrial Treasure Hunter" aesthetic, it transforms mundane clearance data into a premium searching experience.

---

## 🚀 Key Features

*   **Continuous Store Scrutiny**: Automated Playwright-driven agents scan WA (980-994) and OR (970-979) stores every few hours.
*   **The Treasure Dashboard**: A custom-designed, industrial-themed FastAPI dashboard for browsing, filtering, and saving deals.
*   **Premium Membership (Stripe)**: Integrated subscription system ($50/mo) for full database access, historical archives, and advanced search.
*   **Targeted Deal Alerts**: Paid notification system ($10/mo per alert) allowing users to monitor specific categories (e.g., "Flooring") or keywords (e.g., "DeWalt").
*   **Real-Time Dispatch**: Instant email notifications via SendGrid when a "treasure" matches your alert criteria.
*   **Smart Ingestion**: Secure API endpoint for distributed workers to report findings.

---

## 🛠 Technology Stack

*   **Backend**: [FastAPI](https://fastapi.tiangolo.com/) (Async Python)
*   **Automation**: [Playwright](https://playwright.dev/python/) with Stealth Patches
*   **Database**: SQLAlchemy ORM with SQLite (Atomic write-ahead logs)
*   **Payments**: [Stripe](https://stripe.com/) Checkout & Customer Portal
*   **Email**: [SendGrid](https://sendgrid.com/)
*   **Frontend**: Semantic HTML5, Vanilla CSS (Industrial Theme), Jinja2 Templates

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
python -m playwright install chromium
```

### 2. Configuration
Copy `.env.example` to `.env` and fill in your credentials:
```bash
cp .env.example .env
```
Key Variables:
*   `CHEAPSKATER_SESSION_SECRET`: Random string for secure cookies.
*   `STRIPE_SECRET_KEY` / `STRIPE_PUBLISHABLE_KEY`: From your Stripe dashboard.
*   `SENDGRID_API_KEY`: For email notifications.
*   `CHEAPSKATER_INGEST_API_KEY`: Token for securing the ingest endpoint.

### 3. Launching
**Developer / Dashboard Mode:**
```bash
python -m uvicorn app.dashboard:app --reload
```
Open [http://localhost:8000](http://localhost:8000) to see the treasure hunter in action.

**Worker / Scraper Mode:**
```bash
python -m app.main --dashboard
```

---

## 🏗 System Architecture

### 1. The Scraper (`app/main.py`)
Uses Playwright to navigate Lowe's categories, sets the store context via ZIP code, and extracts clearance data. It employs stealth tactics (mouse jitter, random pacing, persistent profiles) to maintain a low profile.

### 2. The Dashboard (`app/dashboard.py`)
The hub of the operation. Handles:
*   **Public/Member Content**: Restricts deep archive access based on Stripe status.
*   **Ingestion**: Receives batch deal data from workers.
*   **Management**: Alert logic and user account settings.

### 3. Notifications (`app/notifications/`)
A dedicated processor that runs after every ingestion batch. It matches incoming deals against user-defined `DealAlert` rules and dispatches emails via the `EmailService`.

### 4. Authentication (`app/auth/`)
Secure middleware for session management, PBKDF2 password hashing, and seamless Stripe integration for "Pro Access" upgrades.

---

## 💰 Subscription Model

*   **Free**: Browse last 24 hours of deals, 5 saved items limit.
*   **Pro Access ($50/mo)**: Unlimited access to the full historical archive, advanced filters, and Excel exports.
*   **Paid Alerts ($10/mo each)**: Custom category or keyword-based instant email notifications.

---

## 📜 Legal & Usage
*This tool is intended for personal research and price monitoring only. Please respect Lowe's robots.txt and usage policies. GloorBot is not affiliated with, authorized, or endorsed by Lowe's Companies, Inc.*

---
**Happy Hunting!** 🤖💰🏚️
