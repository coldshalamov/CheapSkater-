import re

with open('app/static/css/style.css', 'r', encoding='utf-8') as f:
    css = f.read()

# Add spacing and text scale variables
vars_to_add = """
    /* Spacing */
    --space-1: 4px;
    --space-2: 8px;
    --space-3: 12px;
    --space-4: 16px;
    --space-6: 24px;
    --space-8: 32px;
    --space-12: 48px;

    /* Text Scale */
    --text-xs: 0.75rem;
    --text-sm: 0.875rem;
    --text-base: 1rem;
    --text-lg: 1.125rem;
    --text-xl: 1.25rem;
    --text-2xl: 1.5rem;
    --text-3xl: 1.875rem;
    --text-4xl: 2.25rem;
"""
css = css.replace("    --radius-pill: 6px;", "    --radius-pill: 6px;\n" + vars_to_add)

# Transitions
css = css.replace("transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);", "transition: all 0.3s cubic-bezier(0.2, 0.8, 0.2, 1);")
css = css.replace("transition: all 0.2s ease;", "transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);")
css = css.replace("transition: all 0.2s;", "transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);")

# Active states
css = re.sub(r"(\.btn:active\s*\{\s*transform:\s*)translateY\(-?1px\);", r"\1scale(0.97);", css)

# Scrollbars
scrollbar_css = """
/* Custom Scrollbar */
::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}
::-webkit-scrollbar-track {
    background: transparent;
}
::-webkit-scrollbar-thumb {
    background-color: var(--text-muted);
    border-radius: 20px;
    border: 2px solid var(--bg-primary);
}
::-webkit-scrollbar-thumb:hover {
    background-color: var(--text-secondary);
}

"""
css = scrollbar_css + css

# Card Discount Pill
old_discount = """
.deal-card__discount {
    position: absolute;
    top: 16px;
    right: 16px;
    background: var(--danger);
    color: white;
    font-family: var(--font-heading);
    font-weight: 700;
    padding: 4px 12px;
    border-radius: var(--radius-pill);
    font-size: 0.85rem;
    box-shadow: 0 2px 4px rgba(239, 68, 68, 0.3);
}"""
new_discount = """
.deal-card__discount {
    position: absolute;
    top: 16px;
    right: 16px;
    background: linear-gradient(135deg, #FF416C 0%, #FF4B2B 100%);
    color: white;
    font-family: var(--font-heading);
    font-weight: 700;
    padding: 4px 12px;
    border-radius: var(--radius-pill);
    font-size: 0.85rem;
    box-shadow: 0 4px 12px rgba(255, 75, 43, 0.3);
    border: 1px solid rgba(255,255,255,0.2);
    backdrop-filter: blur(4px);
    letter-spacing: 0.5px;
    z-index: 10;
}"""
css = css.replace(old_discount, new_discount)

# Title clamp
css = css.replace("-webkit-line-clamp: 4;", "-webkit-line-clamp: 2;")

# Card Hover Glow
css = re.sub(
    r"\.card:hover\s*\{\s*transform:\s*translateY\(-6px\);\s*box-shadow:\s*var\(--shadow-xl\);\s*\}",
    ".card:hover {\n    transform: translateY(-4px);\n    box-shadow: 0 12px 24px -10px var(--accent-blue-soft), 0 4px 10px -4px rgba(0, 0, 0, 0.05);\n    border-color: rgba(79, 70, 229, 0.2);\n}",
    css
)

# Price spacing
css = css.replace("font-size: 1.75rem;", "font-size: 1.75rem;\n    letter-spacing: -0.04em;")

# Was Price strikethrough
old_was_price = """
.deal-card__was-price {
    text-decoration: line-through;
    color: var(--text-muted);
    font-weight: 600;
}"""
new_was_price = """
.deal-card__was-price {
    position: relative;
    text-decoration: none;
    color: var(--text-muted);
    font-weight: 600;
}
.deal-card__was-price::after {
    content: '';
    position: absolute;
    left: -2px;
    right: -2px;
    top: 50%;
    height: 2px;
    background: var(--danger);
    transform: rotate(-8deg);
    border-radius: 2px;
    opacity: 0.7;
}"""
css = css.replace(old_was_price, new_was_price)

# Product Images multiply
css = css.replace(".deal-card__image img {\n    max-width: 100%;", ".deal-card__image img {\n    max-width: 100%;\n    mix-blend-mode: multiply;")

with open('app/static/css/style.css', 'w', encoding='utf-8') as f:
    f.write(css)

# Update dashboard.html title attribute
with open('app/templates/dashboard.html', 'r', encoding='utf-8') as f:
    html = f.read()

html = html.replace('<a href="{{ group.best_product_url }}" target="_blank">{{ group.title }}</a>', '<a href="{{ group.best_product_url }}" target="_blank" title="{{ group.title }}">{{ group.title }}</a>')

with open('app/templates/dashboard.html', 'w', encoding='utf-8') as f:
    f.write(html)

print("Update V2 complete.")
