"""Centralised selectors for Lowe's scraping and discovery flows."""

# ==== SCRAPE (product grid) ====
PRODUCT_PATH_FRAGMENT = "/pd/"
CARD = (
    "[data-test='product-pod'], [data-test='productPod'], "
    "li:has(a[href*='/pd/']), article:has(a[href*='/pd/'])"
)
CARD_ALT = (
    "[data-test*='product-card'], "
    "section [data-test*='product'] :is(li,article)"
)
TITLE = (
    f":scope a[href*='{PRODUCT_PATH_FRAGMENT}'], "
    ":scope [data-test*='product-title'], :scope h3, :scope h2"
)
PRICE = (
    ":scope [data-test*='price'], :scope [data-testid*='price'], "
    ":scope [aria-label*='$'], :scope [data-test*='current-price']"
)
PRICE_ALT = (
    ":scope [data-test*='value'], :scope [data-testid*='value'], "
    ":scope [data-test*='sale-price']"
)
WAS_PRICE = (
    ":scope [data-test*='was'], :scope [data-testid*='was'], "
    ":scope [class*='was-price'], :scope [data-test*='savings']"
)
AVAIL = (
    ":scope [data-test*='availability'], :scope [data-testid*='availability'], "
    ":scope [data-test*='fulfillment'], :scope [data-test*='pickup']"
)
IMG = ":scope img"
LINK = f":scope a[href*='{PRODUCT_PATH_FRAGMENT}'], :scope a[data-test*='product-link']"
NEXT_BTN = (
    "nav[aria-label='Pagination'] a[rel='next'], "
    "button[aria-label='Next'], .pagination-next a, "
    ".pagination button[aria-label='Next'], [rel='next']"
)
STORE_BADGE = (
    "header [data-test*='store'], header [aria-label*='store'], "
    "[data-test*='store-badge'], a[href*='store-details']"
)

# ==== DISCOVERY (nav + department hubs + store locator) ====
GLOBAL_NAV_BUTTONS = "header nav button, header nav a"
MEGAMENU_LINKS = "div[role='menu'] a[href^='/c/'], div[role='menu'] a[href^='/pl/']"
DEPARTMENT_HUB_LINKS = "main a[href^='/c/'], main a[href^='/pl/']"
PAGE_H1 = "main h1, main header h1"

STORE_LOCATOR_LINK = "a[href*='store-locator'], a[href*='store-directory']"
STORE_SEARCH_INPUT = "input[type='search'], input[placeholder*='city'], input[placeholder*='ZIP']"
STORE_RESULT_ITEM = (
    "[data-store-id], [data-test*='store-card'], "
    "li:has(a[href*='store-details']), a[href*='store-details']"
)
STORE_RESULT_ZIP = ":scope *, [data-zip]"

# Selectors listed here are constant fragments rather than full CSS queries.
NON_SELECTOR_CONSTANTS = {"PRODUCT_PATH_FRAGMENT"}
