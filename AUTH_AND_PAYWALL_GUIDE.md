# CheapSkater Authentication & Paywall Guide

## Current Status

### ✅ What's Built
- **Full authentication system** with login/register
- **Stripe integration** for payments
- **Subscription management** (Free, Basic, Premium plans)
- **Session-based auth** (no JWT needed)
- **Account management** page
- **Pricing page** with Stripe checkout

### ❌ What's NOT Implemented Yet
- **No content is paywalled** - Everything is currently free/public
- **No feature restrictions** - All users see the same content
- **Notifications feature** exists but isn't restricted

---

## How to Create an Account

### Option 1: Via Web UI (Recommended)
1. Go to your site: `https://your-site.com`
2. Click **"Sign In"** in the top navigation
3. Click **"Create an account"** link
4. Fill out the registration form:
   - **Email**: Your email address
   - **Password**: At least 8 characters
   - **Display Name**: Optional
5. Click **"Register"**
6. You'll be automatically logged in and redirected to your account page

### Option 2: Direct URL
Navigate to: `https://your-site.com/auth/register`

---

## Current Authentication Flow

### Registration
```
/auth/register → Fill form → POST /auth/register → Auto-login → /auth/account
```

### Login
```
/auth/login → Fill form → POST /auth/login → Redirect to homepage or `next` URL
```

### Logout
```
/auth/logout → Clear session → Redirect to homepage
```

---

## Subscription Plans

### Plan Structure (from `stripe_integration.py`)

**FREE Plan** (Default)
- No payment required
- Currently has access to everything (no restrictions)

**BASIC Plan** ($9.99/month)
- Stripe checkout required
- Currently has access to everything (no restrictions)

**PREMIUM Plan** ($19.99/month)
- Stripe checkout required
- Currently has access to everything (no restrictions)

### How Subscriptions Work
1. User registers (gets FREE plan automatically)
2. User goes to `/auth/pricing`
3. User clicks "Subscribe" on a paid plan
4. Redirected to Stripe Checkout
5. After payment, Stripe webhook updates subscription
6. User gets access to paid features (when implemented)

---

## What Needs to Be Paywalled?

### Current Features That Could Be Restricted

1. **Notifications/Alerts** (`/notifications`)
   - Currently exists but is open to all
   - Could require BASIC plan

2. **Export to Excel** (Export button on dashboard)
   - Currently free for everyone
   - Could require BASIC plan

3. **Saved Deals** (`/cheapskater`)
   - Currently free for everyone
   - Could limit number of saved deals for FREE users

4. **Advanced Filters**
   - Could restrict certain filters to paid users
   - E.g., custom discount ranges, specific categories

5. **Deal History**
   - Could show last 7 days for FREE
   - Full history for BASIC/PREMIUM

### Recommended Paywall Strategy

**FREE Tier:**
- View all deals (read-only)
- Basic filters (category, state)
- Save up to 10 deals
- No notifications

**BASIC Tier ($9.99/mo):**
- Everything in FREE
- Unlimited saved deals
- Email notifications for new deals
- Export to Excel
- Advanced filters
- 30-day deal history

**PREMIUM Tier ($19.99/mo):**
- Everything in BASIC
- SMS notifications (if implemented)
- Priority support
- Custom deal alerts
- Full deal history (90 days)
- API access (if implemented)

---

## How to Implement Paywall

### Step 1: Check User Subscription

Add this helper function to `app/auth/dependencies.py`:

```python
def require_subscription(min_plan: SubscriptionPlan = SubscriptionPlan.BASIC):
    """Dependency that requires a minimum subscription level."""
    async def _check_subscription(request: Request):
        user = await get_current_user(request)
        
        db_session = next(_get_db_session())
        try:
            auth_service = AuthService(db_session)
            subscription = auth_service.get_subscription(user.id)
            
            if not subscription or not subscription.is_active_subscription():
                # User has no active subscription
                if min_plan != SubscriptionPlan.FREE:
                    raise HTTPException(
                        status_code=403,
                        detail="This feature requires an active subscription"
                    )
            
            # Check if user's plan meets minimum requirement
            plan_hierarchy = {
                SubscriptionPlan.FREE: 0,
                SubscriptionPlan.BASIC: 1,
                SubscriptionPlan.PREMIUM: 2,
            }
            
            user_plan_level = plan_hierarchy.get(subscription.plan if subscription else SubscriptionPlan.FREE, 0)
            required_level = plan_hierarchy.get(min_plan, 0)
            
            if user_plan_level < required_level:
                raise HTTPException(
                    status_code=403,
                    detail=f"This feature requires a {min_plan.value} subscription"
                )
            
            return user
        finally:
            db_session.close()
    
    return Depends(_check_subscription)
```

### Step 2: Protect Routes

Example - Protect notifications:

```python
# In app/notifications/routes.py
from app.auth.dependencies import require_subscription
from app.auth.models import SubscriptionPlan

@router.get("/notifications")
async def notifications_page(
    request: Request,
    user: User = require_subscription(SubscriptionPlan.BASIC)  # Require BASIC plan
):
    # Only users with BASIC or PREMIUM can access
    ...
```

### Step 3: Protect Features in Templates

Add subscription check in templates:

```html
{% if user and user.subscription and user.subscription.plan in ['basic', 'premium'] %}
    <button onclick="exportToExcel()">Export to Excel</button>
{% else %}
    <a href="/auth/pricing" class="btn btn-primary">
        Upgrade to Export
    </a>
{% endif %}
```

### Step 4: Add Upgrade Prompts

When users hit a paywalled feature:

```html
<div class="paywall-notice">
    <h3>🔒 Premium Feature</h3>
    <p>Upgrade to BASIC to unlock notifications and more!</p>
    <a href="/auth/pricing" class="btn btn-primary">View Plans</a>
</div>
```

---

## Testing the Auth System

### 1. Create a Test Account
```bash
# Visit your site
https://your-site.com/auth/register

# Fill in:
Email: test@example.com
Password: testpassword123
Display Name: Test User
```

### 2. Test Login/Logout
- Login at `/auth/login`
- Check that navigation shows "Account" instead of "Sign In"
- Logout at `/auth/logout`
- Verify you're logged out

### 3. Test Subscription Flow (Requires Stripe)
- Login
- Go to `/auth/pricing`
- Click "Subscribe" on BASIC plan
- Complete Stripe checkout (use test card: `4242 4242 4242 4242`)
- Verify subscription shows in `/auth/account`

---

## Stripe Configuration

### Required Environment Variables

```bash
# In your .env or Render environment
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# Plan Price IDs (from Stripe Dashboard)
STRIPE_BASIC_PRICE_ID=price_...
STRIPE_PREMIUM_PRICE_ID=price_...
```

### Stripe Test Mode
- Use test API keys (start with `sk_test_` and `pk_test_`)
- Test card: `4242 4242 4242 4242` (any future date, any CVC)
- No real money is charged in test mode

---

## Quick Start Checklist

- [ ] **Create your first account** via `/auth/register`
- [ ] **Test login/logout** to verify auth works
- [ ] **Configure Stripe** (if you want payments)
- [ ] **Decide what to paywall** (notifications, exports, etc.)
- [ ] **Implement paywall checks** using `require_subscription()`
- [ ] **Add upgrade prompts** in the UI
- [ ] **Test the full flow** from free → paid

---

## Current State Summary

**Authentication:** ✅ Fully working
**Subscriptions:** ✅ Fully working (with Stripe)
**Paywall:** ❌ Not implemented (everything is free)

**To make money, you need to:**
1. Decide what features to restrict
2. Add subscription checks to those features
3. Add upgrade prompts in the UI
4. Configure Stripe with real API keys
5. Set up pricing in Stripe Dashboard

---

## Need Help?

**Can't create an account?**
- Check that the database is accessible
- Check server logs for errors
- Verify `/auth/register` page loads

**Stripe not working?**
- Verify environment variables are set
- Check Stripe Dashboard for test mode
- Review webhook logs in Stripe

**Want to paywall a feature?**
- Use `require_subscription()` dependency
- Add plan checks in templates
- Show upgrade prompts for free users
