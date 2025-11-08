"""Selectors used for parsing retailer pages.

How to capture new selectors:
1. Set a store by ZIP in a real browser session so inventory matches expectations.
2. Open a category URL that lists products for that store.
3. In Chrome DevTools, right-click the desired element and choose Copy → Copy selector
   for each of CARD, TITLE, PRICE, WAS_PRICE, AVAIL, IMG, LINK, NEXT_BTN, STORE_BADGE.
4. Playwright's :has-text() helper can be convenient, but always keep a pure CSS
   fallback selector for resiliency.
"""

CARD = "main :is(li,article,div):has(a[href*='/pd/'])"
TITLE = ":scope a[href*='/pd/'], :scope h3, :scope h2"
PRICE = ":scope :is([data-test*='price'], [data-automation-id*='price'], .price, .sale-price, .ProductPrice__price, [aria-label*='$'])"
WAS_PRICE = ":scope :is([data-test*='was'], .was-price, .strike, [aria-label*='Was'])"
AVAIL = ":scope :is([data-test*='availability'], [data-automation-id*='availability'], .availability, [aria-label*='stock'])"
IMG = ":scope img"
LINK = ":scope a[href*='/pd/']"
NEXT_BTN = "nav[aria-label='Pagination'] a[rel='next'], button[aria-label='Next'], .pagination-next a, .pagination button[aria-label='Next']"
STORE_BADGE = "header :is([aria-label*='My Store'], [data-test*='store'], [data-automation-id*='store'], a[href*='store-details'])"
