"""
Add username field to users table.

Usage:
    python scripts/add_username_field.py
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from app.storage.db import get_engine, make_session, resolve_database_file
from app.logging_config import get_logger

LOGGER = get_logger(__name__)


def add_username_field():
    """Add username column to users table if it doesn't exist."""
    # Get database connection
    BASE_PATH = Path(__file__).resolve().parent.parent
    FALLBACK_DATABASE_FILE = (BASE_PATH / "orwa_lowes.sqlite").resolve()
    DATABASE_FILE = resolve_database_file(fallback=FALLBACK_DATABASE_FILE)
    
    engine = get_engine(str(DATABASE_FILE))
    
    LOGGER.info(f"Adding username field to users table in {DATABASE_FILE}")
    
    with engine.connect() as conn:
        # Check if column already exists
        result = conn.execute(text("PRAGMA table_info(users)"))
        columns = [row[1] for row in result]
        
        if 'username' in columns:
            LOGGER.info("✅ Username column already exists")
            return
        
        # Add the column (without UNIQUE constraint - SQLite limitation)
        LOGGER.info("Adding username column...")
        conn.execute(text("""
            ALTER TABLE users 
            ADD COLUMN username VARCHAR(50)
        """))
        conn.commit()
        
        # Create unique index
        LOGGER.info("Creating unique index on username...")
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username 
            ON users(username)
        """))
        conn.commit()
        
        LOGGER.info("✅ Username field added successfully!")
        LOGGER.info("Users can now set their username in account settings.")


if __name__ == "__main__":
    add_username_field()
