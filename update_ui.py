import re

# Read the CSS
with open('app/static/css/style.css', 'r', encoding='utf-8') as f:
    css = f.read()

# Typography
css = css.replace("@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&family=Fredoka:wght@400;500;600;700&display=swap');", "@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');")
css = css.replace("--font-heading: 'Fredoka', system-ui, sans-serif;", "--font-heading: 'Inter', system-ui, sans-serif;")
css = css.replace("--font-body: 'Nunito', system-ui, sans-serif;", "--font-body: 'Inter', system-ui, sans-serif;")

# Colors
css = css.replace("--bg-secondary: #f0f4f8;", "--bg-secondary: #f8fafc;")
css = css.replace("--accent-blue: #2563EB;", "--accent-blue: #4f46e5;")
css = css.replace("--accent-blue-dark: #1E40AF;", "--accent-blue-dark: #3730a3;")
css = css.replace("--accent-blue-light: #60A5FA;", "--accent-blue-light: #818cf8;")
css = css.replace("--accent-blue-soft: rgba(37, 99, 235, 0.12);", "--accent-blue-soft: rgba(79, 70, 229, 0.12);")

# Radii
css = css.replace("--radius-sm: 8px;", "--radius-sm: 4px;")
css = css.replace("--radius-md: 12px;", "--radius-md: 6px;")
css = css.replace("--radius-lg: 16px;", "--radius-lg: 8px;")
css = css.replace("--radius-xl: 24px;", "--radius-xl: 12px;")
css = css.replace("--radius-pill: 9999px;", "--radius-pill: 6px;")

# Shadows
css = css.replace("--shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);", "--shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);")
css = css.replace("--shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05);", "--shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -2px rgba(0, 0, 0, 0.03);")
css = css.replace("--shadow-xl: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);", "--shadow-xl: 0 20px 25px -5px rgba(0, 0, 0, 0.05), 0 10px 10px -5px rgba(0, 0, 0, 0.03);")

# Background images
css = css.replace("background-image: url('../img/hero-gradient.png');", "/* background-image: url('../img/hero-gradient.png'); */")
css = css.replace("background-image: url('../img/header-pattern.png');", "/* background-image: url('../img/header-pattern.png'); */")

# Header fixes
css = re.sub(r"background: linear-gradient.*?var\(--accent-blue\) 100%\);", "background: #ffffff; color: var(--text-primary); border-bottom: 1px solid #e2e8f0;", css)
css = css.replace("color: white;\n    position: relative;", "position: relative;")
css = css.replace("border-radius: 0 0 var(--radius-xl) var(--radius-xl);", "border-radius: 0;")
css = css.replace(".nav-link {\n    color: rgba(255, 255, 255, 0.9);", ".nav-link {\n    color: var(--text-secondary);")
css = css.replace(".nav-link:hover {\n    background: rgba(255, 255, 255, 0.15);\n    color: white;\n}", ".nav-link:hover {\n    background: var(--bg-secondary);\n    color: var(--text-primary);\n}")
css = css.replace(".nav-link.active {\n    background: white;\n    color: var(--accent-blue);\n    box-shadow: var(--shadow-sm);\n}", ".nav-link.active {\n    background: var(--accent-blue-soft);\n    color: var(--accent-blue);\n    box-shadow: none;\n}")
css = css.replace("border-radius: 0 0 16px 16px;", "border-radius: 0;")

# Logo fixes
css = re.sub(r"\.brand-logo \{[^}]*\}", ".brand-logo { position: relative; top: 0; left: 0; height: 36px; width: 36px; object-fit: contain; margin-right: 12px; box-shadow: none; }", css)
css = css.replace(".brand-name {\n    display: none;\n    /* Hide text, logo is iconic enough */\n}", ".brand-name { display: block; font-weight: 700; font-size: 1.25rem; color: var(--text-primary); }")
css = css.replace("margin-left: 120px;", "margin-left: auto;") # Move nav links to right
css = css.replace(".brand-link {\n    display: flex;", ".brand-link {\n    display: flex;\n    align-items: center;")

# Card fixes
css = css.replace("backdrop-filter: var(--glass-blur);", "/* backdrop-filter: var(--glass-blur); */")
css = css.replace("border: 1px solid white;", "border: 1px solid #e2e8f0;")

with open('app/static/css/style.css', 'w', encoding='utf-8') as f:
    f.write(css)

# Read Base HTML
with open('app/templates/base.html', 'r', encoding='utf-8') as f:
    base_html = f.read()

base_html = base_html.replace("https://fonts.googleapis.com/css2?family=Fredoka:wght@400;500;600;700&family=Nunito:wght@400;600;700&display=swap", "https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap")

with open('app/templates/base.html', 'w', encoding='utf-8') as f:
    f.write(base_html)

# Clean up Dashboard Emojis
with open('app/templates/dashboard.html', 'r', encoding='utf-8') as f:
    dashboard_html = f.read()

dashboard_html = dashboard_html.replace("👑 Premium Account: Live Deals", "Premium Account: Live Deals")
dashboard_html = dashboard_html.replace("⚡ Pro Account: Live Deals", "Pro Account: Live Deals")
dashboard_html = dashboard_html.replace("ℹ️ Sorting:", "Sorting:")
dashboard_html = dashboard_html.replace("🔥 Deals this cheap go fast!", "Deals this cheap go fast!")

with open('app/templates/dashboard.html', 'w', encoding='utf-8') as f:
    f.write(dashboard_html)

print("Update complete.")
