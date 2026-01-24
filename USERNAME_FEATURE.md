# Username/Handle Feature Implementation

## Summary

Added the ability for users to set a custom username/handle on the website instead of just showing the first letter of their email.

## Changes Made

### 1. Database Schema ✅

**File**: `app/auth/models.py`
- Added `username` field to User model (line 42):
  ```python
  # Username/handle
  username: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True, index=True)
  ```

**Migration**: `scripts/add_username_field.py` ✅
- Successfully ran migration to add username column to database
- Created unique index on username field

### 2. Backend API Endpoint (NEEDS TO BE ADDED)

**File**: `app/auth/routes.py`
**Location**: After the `account_page` function (around line 167)

Add this code:

```python
class UpdateUsernameRequest(BaseModel):
    username: str


@router.post("/api/update-username")
async def update_username(request: Request, data: UpdateUsernameRequest):
    """Update user's username/handle."""
    import re
    
    user = await get_optional_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Validate username
    username = data.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username cannot be empty")
    
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    
    if len(username) > 50:
        raise HTTPException(status_code=400, detail="Username must be 50 characters or less")
    
    # Only allow alphanumeric, underscore, and hyphen
    if not re.match(r'^[a-zA-Z0-9_-]+$', username):
        raise HTTPException(status_code=400, detail="Username can only contain letters, numbers, underscores, and hyphens")
    
    db_session = next(_get_db_session())
    try:
        # Check if username is already taken
        existing = db_session.query(User).filter(User.username == username).first()
        if existing and existing.id != user.id:
            raise HTTPException(status_code=400, detail="Username is already taken")
        
        # Update username
        db_user = db_session.query(User).filter(User.id == user.id).first()
        if not db_user:
            raise HTTPException(status_code=404, detail="User not found")
        
        db_user.username = username
        db_session.commit()
        
        return {"success": True, "username": username}
    except HTTPException:
        raise
    except Exception as e:
        db_session.rollback()
        LOGGER.error(f"Error updating username: {e}")
        raise HTTPException(status_code=500, detail="Failed to update username")
    finally:
        db_session.close()
```

### 3. Frontend - Account Page (NEEDS TO BE UPDATED)

**File**: `app/templates/auth/account.html`

Add a new card for username settings after the Profile Card (around line 39):

```html
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
```

Add this JavaScript at the end of the file (before `{% endblock %}`):

```html
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
```

### 4. Update Display Logic (OPTIONAL ENHANCEMENTS)

**Current**: Profile card shows `{{ (user.display_name or user.email)[0]|upper }}`

**Suggested**: Update to show username when available:

```html
{{ (user.username or user.display_name or user.email)[0]|upper }}
```

And for the display name:

```html
<p style="font-weight: 700; font-size: 1.125rem;">
    {% if user.username %}
    @{{ user.username }}
    {% else %}
    {{ user.display_name or 'GloorBot Member' }}
    {% endif %}
</p>
```

## Username Validation Rules

- **Length**: 3-50 characters
- **Characters**: Letters (a-z, A-Z), numbers (0-9), underscores (_), and hyphens (-)
- **Uniqueness**: Must be unique across all users
- **Optional**: Users can leave it blank

## Testing

1. Navigate to `/auth/account`
2. Enter a username in the new form
3. Click "Update Username"
4. Verify success message appears
5. Reload page to see updated username
6. Try setting a duplicate username (should fail)
7. Try invalid characters (should fail)
8. Try too short/long username (should fail)

## Next Steps

1. Manually add the API endpoint code to `app/auth/routes.py`
2. Manually add the username form to `app/templates/auth/account.html`
3. Restart the application
4. Test the functionality
5. (Optional) Update other places where user display name is shown to use username

## Files Created

- ✅ `scripts/add_username_field.py` - Database migration script (already run)
- ✅ `app/auth/username_update.py` - Helper module (can be deleted, code should go in routes.py)
- ✅ `USERNAME_FEATURE.md` - This documentation file
