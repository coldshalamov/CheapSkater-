"""
Quick script to verify admin account exists and show login details.
"""

from app.storage.db import get_engine, make_session, resolve_database_file
from app.auth.models import User, Subscription
from pathlib import Path

def verify_admin():
    """Verify admin account exists and show details."""
    
    BASE_PATH = Path(__file__).resolve().parent.parent
    FALLBACK_DATABASE_FILE = (BASE_PATH / "orwa_lowes.sqlite").resolve()
    DATABASE_FILE = resolve_database_file(fallback=FALLBACK_DATABASE_FILE)
    
    engine = get_engine(str(DATABASE_FILE))
    session_factory = make_session(engine)
    session = session_factory()
    
    try:
        user = session.query(User).filter(User.email == '93robingattis@gmail.com').first()
        
        if not user:
            print('❌ Admin user not found!')
            return False
        
        sub = session.query(Subscription).filter(Subscription.user_id == user.id).first()
        
        print('=' * 60)
        print('✅ ADMIN ACCOUNT VERIFIED')
        print('=' * 60)
        print(f'Email: {user.email}')
        print(f'Password: Alphonse5150$')
        print(f'Is Admin: {user.is_admin}')
        print(f'Is Active: {user.is_active}')
        if sub:
            print(f'Subscription Plan: {sub.plan.value}')
            print(f'Subscription Status: {sub.status.value}')
            if sub.current_period_end:
                print(f'Valid Until: {sub.current_period_end.strftime("%B %d, %Y")}')
        print('=' * 60)
        print('\nYou can now log in at: http://localhost:8000/auth/login')
        print('=' * 60)
        return True
        
    except Exception as e:
        print(f'❌ ERROR: {e}')
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()

if __name__ == "__main__":
    verify_admin()
