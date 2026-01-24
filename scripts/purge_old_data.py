"""
Database maintenance script for purging old clearance data.

Usage:
    python scripts/purge_old_data.py --days 7
    python scripts/purge_old_data.py --days 1 --dry-run
"""

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.storage.db import get_engine, make_session, resolve_database_file
from app.storage.models_sql import Observation, StorePriceHistory
from app.logging_config import get_logger

LOGGER = get_logger(__name__)


def purge_old_data(days: int, dry_run: bool = False):
    """
    Purge observations and price history older than the specified number of days.
    
    Args:
        days: Number of days to keep (anything older will be deleted)
        dry_run: If True, only show what would be deleted without actually deleting
    """
    # Get database connection
    BASE_PATH = Path(__file__).resolve().parent.parent
    FALLBACK_DATABASE_FILE = (BASE_PATH / "orwa_lowes.sqlite").resolve()
    DATABASE_FILE = resolve_database_file(fallback=FALLBACK_DATABASE_FILE)
    
    engine = get_engine(str(DATABASE_FILE))
    session_factory = make_session(engine)
    
    # Calculate cutoff date
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    LOGGER.info(f"Purging data older than {days} days (before {cutoff_date.isoformat()})")
    
    with session_factory() as session:
        # Count observations to be deleted
        obs_count = session.query(Observation).filter(
            Observation.ts_utc < cutoff_date
        ).count()
        
        # Count price history to be deleted
        history_count = session.query(StorePriceHistory).filter(
            StorePriceHistory.started_at < cutoff_date
        ).count()
        
        total_count = obs_count + history_count
        
        if total_count == 0:
            LOGGER.info("No records found older than the specified date.")
            return
        
        LOGGER.info(f"Found {obs_count:,} observations and {history_count:,} price history records to delete")
        LOGGER.info(f"Total records to delete: {total_count:,}")
        
        if dry_run:
            LOGGER.info("DRY RUN - No data will be deleted")
            return
        
        # Confirm deletion
        print(f"\n⚠️  WARNING: This will permanently delete {total_count:,} records!")
        print(f"   - {obs_count:,} observations")
        print(f"   - {history_count:,} price history entries")
        print(f"   - Data older than {cutoff_date.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        
        response = input("\nAre you sure you want to continue? (yes/no): ")
        
        if response.lower() != 'yes':
            LOGGER.info("Purge cancelled by user")
            return
        
        # Delete observations
        LOGGER.info("Deleting observations...")
        deleted_obs = session.query(Observation).filter(
            Observation.ts_utc < cutoff_date
        ).delete(synchronize_session=False)
        
        # Delete price history
        LOGGER.info("Deleting price history...")
        deleted_history = session.query(StorePriceHistory).filter(
            StorePriceHistory.started_at < cutoff_date
        ).delete(synchronize_session=False)
        
        # Commit changes
        session.commit()
        
        LOGGER.info(f"✅ Purge complete!")
        LOGGER.info(f"   - Deleted {deleted_obs:,} observations")
        LOGGER.info(f"   - Deleted {deleted_history:,} price history entries")
        LOGGER.info(f"   - Total deleted: {deleted_obs + deleted_history:,} records")
        
        # Run VACUUM to reclaim space
        print("\nRunning VACUUM to reclaim disk space...")
        session.execute("VACUUM")
        LOGGER.info("Database optimized")


def main():
    parser = argparse.ArgumentParser(
        description="Purge old clearance data from the database"
    )
    parser.add_argument(
        "--days",
        type=int,
        required=True,
        help="Delete data older than this many days"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting"
    )
    
    args = parser.parse_args()
    
    if args.days < 1:
        print("Error: --days must be at least 1")
        sys.exit(1)
    
    purge_old_data(args.days, args.dry_run)


if __name__ == "__main__":
    main()
