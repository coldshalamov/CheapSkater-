"""Centralised selectors for Lowe's scraping and discovery flows."""

# ==== SCRAPE (product grid) ====
CARD = "main :is(li,article,div):has(a[href*='/pd/'])"
CARD_ALT = "section [data-test*='product'] a[href*='/pd/']"
TITLE = ":scope a[href*='/pd/'], :scope h3, :scope h2"
PRICE = ":scope :is([data-test*='price'], [data-automation-id*='price'], .price, .sale-price, .ProductPrice__price, [aria-label*='$'])"
PRICE_ALT = ":scope [data-testid*='price'], :scope [aria-label^='$']"
WAS_PRICE = ":scope :is([data-test*='was'], .was-price, .strike, [aria-label*='Was'])"
AVAIL = ":scope :is([data-test*='availability'], [data-automation-id*='availability'], .availability, [aria-label*='stock'])"
IMG = ":scope img"
LINK = ":scope a[href*='/pd/']"
NEXT_BTN = "nav[aria-label='Pagination'] a[rel='next'], button[aria-label='Next'], .pagination-next a, .pagination button[aria-label='Next']"
STORE_BADGE = "header :is([aria-label*='My Store'], [data-test*='store'], [data-automation-id*='store'], a[href*='store-details'])"

# ==== DISCOVERY (nav + department hubs + store locator) ====
GLOBAL_NAV_BUTTONS = "header nav button, header nav a"
MEGAMENU_LINKS = "div[role='menu'] a[href^='/c/'], div[role='menu'] a[href^='/pl/']"
DEPARTMENT_HUB_LINKS = "main a[href^='/c/'], main a[href^='/pl/']"
PAGE_H1 = "main h1, main header h1"

STORE_LOCATOR_LINK = "a[href*='store-locator'], a[href*='store-directory']"
STORE_SEARCH_INPUT = "input[type='search'], input[placeholder*='city'], input[placeholder*='ZIP']"
STORE_RESULT_ITEM = "[data-store-id], li:has(a[href*='store-details']), a[href*='store-details']"
STORE_RESULT_ZIP = ":scope *, [data-zip]"
