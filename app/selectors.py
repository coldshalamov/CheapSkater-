"""Selectors used for parsing retailer pages.

How to capture new selectors:
1. Set a store by ZIP in a real browser session so inventory matches expectations.
2. Open a category URL that lists products for that store.
3. In Chrome DevTools, right-click the desired element and choose Copy → Copy selector
   for each of CARD, TITLE, PRICE, WAS_PRICE, AVAIL, IMG, LINK, NEXT_BTN, STORE_BADGE.
4. Playwright's :has-text() helper can be convenient, but always keep a pure CSS
   fallback selector for resiliency.
"""

CARD = "TODO_CARD_SELECTOR"
TITLE = "TODO_TITLE_SELECTOR"
PRICE = "TODO_PRICE_SELECTOR"
WAS_PRICE = "TODO_WAS_PRICE_SELECTOR"
AVAIL = "TODO_AVAIL_SELECTOR"
IMG = "TODO_IMG_SELECTOR"
LINK = "TODO_LINK_SELECTOR"
NEXT_BTN = "TODO_NEXT_BUTTON_SELECTOR"
STORE_BADGE = "TODO_STORE_BADGE_SELECTOR"
