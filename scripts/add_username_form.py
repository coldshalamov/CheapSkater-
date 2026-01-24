"""Add username form to account page."""

import sys
from pathlib import Path

account_file = Path("app/templates/auth/account.html")

# Read the file
with open(account_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Username card HTML to insert after Profile Card
username_card = '''
        <!-- Username Settings Card -->
        <div class="account-card">
            <div class="card-header">
                <h2 style="font-size: 1.1rem; font-weight: 700;">Username</h2>
            </div>
            <div class="card-body">
                <p style="color: var(--text-secondary); font-size: 0.9rem; margin-bottom: 1rem;">
                    {% if user.username %}
                    Your username: <strong>@{{ user.username }}</strong>
                    {% else %}
                    Set a custom username to personalize your profile.
                    {% endif %}
                </p>
                <form id="username-form" style="display: flex; gap: 0.75rem; flex-direction: column;">
                    <input 
                        type="text" 
                        id="username-input" 
                        name="username" 
                        placeholder="Enter username (e.g., deal_hunter_2026)"
                        value="{{ user.username or '' }}"
                        pattern="[a-zA-Z0-9_-]+"
                        minlength="3"
                        maxlength="50"
                        style="padding: 0.75rem; border: 1px solid var(--border-color); border-radius: var(--radius-md); font-size: 0.9rem;"
                        required
                    >
                    <small style="color: var(--text-muted); font-size: 0.8rem;">
                        3-50 characters. Letters, numbers, underscores, and hyphens only.
                    </small>
                    <button type="submit" class="btn btn-primary">Update Username</button>
                    <div id="username-message" style="display: none; padding: 0.75rem; border-radius: var(--radius-md); font-size: 0.9rem;"></div>
                </form>
            </div>
        </div>

'''

# JavaScript to add before {% endblock %}
username_js = '''
<script>
document.getElementById('username-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const username = document.getElementById('username-input').value.trim();
    const messageEl = document.getElementById('username-message');
    const submitBtn = e.target.querySelector('button[type="submit"]');
    
    // Disable button
    submitBtn.disabled = true;
    submitBtn.textContent = 'Updating...';
    
    try {
        const response = await fetch('/auth/api/update-username', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ username })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            messageEl.style.display = 'block';
            messageEl.style.background = 'var(--success-soft)';
            messageEl.style.color = 'var(--success)';
            messageEl.textContent = `✅ Username updated to @${data.username}`;
            
            // Reload page after 1 second to show updated username
            setTimeout(() => window.location.reload(), 1000);
        } else {
            messageEl.style.display = 'block';
            messageEl.style.background = '#fee2e2';
            messageEl.style.color = '#b91c1c';
            messageEl.textContent = `❌ ${data.detail || 'Failed to update username'}`;
        }
    } catch (error) {
        messageEl.style.display = 'block';
        messageEl.style.background = '#fee2e2';
        messageEl.style.color = '#b91c1c';
        messageEl.textContent = '❌ Network error. Please try again.';
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Update Username';
    }
});
</script>

{% endblock %}'''

# Insert username card after Profile Card (after the first </div> closing account-card)
marker1 = '        <!-- Subscription Card -->'
if marker1 in content:
    content = content.replace(marker1, username_card + marker1)
else:
    print("❌ Could not find Profile Card marker")
    sys.exit(1)

# Replace {% endblock %} with JavaScript + {% endblock %}
if '{% endblock %}' in content:
    content = content.replace('{% endblock %}', username_js)
else:
    print("❌ Could not find endblock marker")
    sys.exit(1)

# Write back
with open(account_file, 'w', encoding='utf-8') as f:
    f.write(content)

print("✅ Successfully added username form to account page")
