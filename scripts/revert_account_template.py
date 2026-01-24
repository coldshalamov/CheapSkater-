"""Revert account.html to remove username form."""
with open('app/templates/auth/account.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Remove username card and JavaScript
new_lines = []
skip = False
for i, line in enumerate(lines):
    # Skip the username card
    if '<!-- Username Settings Card -->' in line:
        skip = True
    elif skip and '<!-- Subscription Card -->' in line:
        skip = False
    
    # Skip the username JavaScript
    if '<script>' in line and i > 10:  # The username script
        # Check if next few lines contain username-form
        check_lines = ''.join(lines[i:min(i+5, len(lines))])
        if 'username-form' in check_lines:
            skip = True
    elif skip and '</script>' in line:
        skip = False
        continue  # Skip the closing script tag too
    
    if not skip:
        new_lines.append(line)

# Revert profile display
final_lines = []
for line in new_lines:
    # Revert avatar initial
    line = line.replace('{{ (user.username or user.display_name or user.email)[0]|upper }}', 
                       '{{ (user.display_name or user.email)[0]|upper }}')
    
    # Revert display name - remove the username conditional
    if '{% if user.username %}' in line:
        continue
    if '@{{ user.username }}' in line:
        continue
    if '{% else %}' in line and i > 0 and 'user.username' in ''.join(new_lines[max(0,i-5):i]):
        continue
    if '{% endif %}' in line and i > 0 and 'user.username' in ''.join(new_lines[max(0,i-10):i]):
        # Replace with simple display
        final_lines.append('                        <p style="font-weight: 700; font-size: 1.125rem;">{{ user.display_name or \'GloorBot Member\' }}\n')
        final_lines.append('                        </p>\n')
        continue
    
    final_lines.append(line)

with open('app/templates/auth/account.html', 'w', encoding='utf-8') as f:
    f.writelines(final_lines)

print("✅ Reverted account.html template")
