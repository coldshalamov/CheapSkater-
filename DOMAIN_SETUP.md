# Domain Setup Guide: lowebot.shop -> CheapSkater

You do **NOT** need to change any Python code for this to work. This is purely a configuration task.

## The Two Ways to Do This

You have two options. Option 1 is "Professional" (the URL stays `lowebot.shop`). Option 2 is "Simple" (the URL changes to `cheapskater.onrender.com`).

### Option 1: The "Pro" Way (Custom Domain)
*This makes your site load at `https://lowebot.shop` and stay there.*

1.  **Go to Render Dashboard**:
    *   Select your "CheapSkater" service.
    *   Go to **Settings** -> **Custom Domains**.
    *   Click **Add Custom Domain**.
    *   Enter `lowebot.shop`.

2.  **Update your DNS (Namecheap/GoDaddy/etc)**:
    *   Render will tell you exactly what to add. usually:
    *   **Type**: `CNAME`
    *   **Host**: `www`
    *   **Value**: `cheapskater.onrender.com`
    *   *(For the root domain `lowebot.shop`, Render usually asks for an `A` record or `ANAME`/`ALIAS` record if your provider supports it. Check Render's instructions exactly).*

3.  **Wait**:
    *   Render will verify the domain and issue a free SSL certificate (HTTPS). This takes 5-30 minutes.

---

### Option 2: The "Simple Redirect" Way
*This makes `lowebot.shop` instantly jump to `cheapskater.onrender.com`.*

1.  **Go to your Domain Registrar** (where you bought the domain).
2.  Look for **"URL Forwarding"** or **"Redirects"**.
3.  Add a rule:
    *   **Source**: `@` (or `lowebot.shop`)
    *   **Target**: `https://cheapskater.onrender.com`
    *   **Type**: `301 Permanent` (or `302 Temporary`)
4.  **Wait**:
    *   Configuring this updates DNS records behind the scenes.
    *   **It can take 1-24 hours** for this to propagate globally, though typically it works within 30-60 minutes.
    *   Try opening an "Incognito" window to test, as your browser caches the "broken" state.

## Troubleshooting
* "It's not working yet": If you only set it up 30 minutes ago, **wait**. DNS is a global system and takes time to update.
* "Non-existent domain": This means the records haven't propagated to your ISP yet.
