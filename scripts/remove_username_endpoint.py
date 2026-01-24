"""Remove username endpoint from routes."""
with open('app/auth/routes.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find and remove the username-related code
new_lines = []
skip = False
for i, line in enumerate(lines):
    if 'class UpdateUsernameRequest' in line:
        skip = True
    elif skip and '@router.get("/pricing"' in line:
        skip = False
    
    if not skip:
        new_lines.append(line)

with open('app/auth/routes.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print("✅ Removed username endpoint from routes.py")
