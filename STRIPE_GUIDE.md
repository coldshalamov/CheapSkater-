# Stripe & Deployment Update Guide

## 1. Deploy Your Code
You **MUST** deploy the latest code to Render for the webhook to work. The webhook points to:
`https://cheapskater.onrender.com/auth/webhook/stripe`

If this code is not live, Stripe cannot send payment confirmations to your database.

## 2. Update Render Environment Variables
Setting `.env` locally does NOT update your production server. Go to your [Render Dashboard](https://dashboard.render.com), find your service, and add/update these environment variables:

| Key | Value |
|-----|-------|
| Key | Value |
|-----|-------|
| `STRIPE_SECRET_KEY` | *(Get from your local .env)* |
| `STRIPE_PUBLISHABLE_KEY` | *(Get from your local .env)* |
| `STRIPE_WEBHOOK_SECRET` | *(Get from your local .env)* |
| `STRIPE_PRICE_BASIC` | `price_1SsT14B35KvstLFM3y4rCRz6` |
| `STRIPE_PRICE_PRO` | `price_1SsT15B35KvstLFMEccOG5TN` |
| `STRIPE_PRICE_PREMIUM` | `price_1SsT17B35KvstLFMPR1tYMuH` |

## 3. Verify
Once deployed and variables are set:
1. Go to `https://cheapskater.onrender.com/auth/pricing`
2. Click "Subscribe" on the Pro plan ($50).
3. The real Stripe Checkout page should appear.
4. After payment, you should be redirected back and your account icon should show "Pro" (or you can check via `/auth/account`).
