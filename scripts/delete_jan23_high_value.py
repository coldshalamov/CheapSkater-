"""
One-off script to delete items with 'price_was' > $1000 AND older than Jan 23, 2026.

Usage:
    python scripts/delete_jan23_high_value.py
    python scripts/delete_jan23_high_value.py --dry-run
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.storage.db import get_engine, make_session, resolve_database_file
from app.storage.models_sql import Observation, StorePriceHistory
from app.logging_config import get_logger

LOGGER = get_logger(__name__)


def cleanup_high_value_old_items(dry_run: bool = False):
    # Configuration
    CUTOFF_DATE = datetime(2026, 1, 23, tzinfo=timezone.utc)
    PRICE_THRESHOLD = 1000.0

    # Get database connection
    BASE_PATH = Path(__file__).resolve().parent.parent
    FALLBACK_DATABASE_FILE = (BASE_PATH / "orwa_lowes.sqlite").resolve()
    DATABASE_FILE = resolve_database_file(fallback=FALLBACK_DATABASE_FILE)

    LOGGER.info(f"Connecting to database: {DATABASE_FILE}")

    engine = get_engine(str(DATABASE_FILE))
    session_factory = make_session(engine)

    with session_factory() as session:
        # 1. Analyze Observations
        obs_query = session.query(Observation).filter(
            Observation.price_was > PRICE_THRESHOLD, Observation.ts_utc < CUTOFF_DATE
        )
        obs_count = obs_query.count()

        # 2. Analyze Price History
        hist_query = session.query(StorePriceHistory).filter(
            StorePriceHistory.price_was > PRICE_THRESHOLD,
            StorePriceHistory.started_at < CUTOFF_DATE,
        )
        hist_count = hist_query.count()

        total_count = obs_count + hist_count

        LOGGER.info(
            f"Criteria: price_was > ${PRICE_THRESHOLD} AND older than {CUTOFF_DATE.date()}"
        )
        LOGGER.info(f"Found {obs_count:,} observations matching criteria")
        LOGGER.info(f"Found {hist_count:,} price history records matching criteria")
        LOGGER.info(f"Total records to delete: {total_count:,}")

        if total_count == 0:
            LOGGER.info("No records found. Exiting.")
            return

        if dry_run:
            LOGGER.info("DRY RUN - No data will be deleted")
            # Print a few examples
            if obs_count > 0:
                example = obs_query.first()
                LOGGER.info(
                    f"Example Observation: SKU={example.sku} Title='{example.title}' PriceWas=${example.price_was} Date={example.ts_utc}"
                )
            return

        # Confirm deletion
        print(f"\n⚠️  WARNING: This will permanently delete {total_count:,} records!")
        response = input("\nAre you sure you want to continue? (yes/no): ")

        if response.lower() != "yes":
            LOGGER.info("Operation cancelled by user")
            return

        # Execute Deletion
        LOGGER.info("Deleting observations...")
        deleted_obs = obs_query.delete(synchronize_session=False)

        LOGGER.info("Deleting price history...")
        deleted_hist = hist_query.delete(synchronize_session=False)

        session.commit()

        LOGGER.info(f"✅ Cleanup complete!")
        LOGGER.info(f"   - Deleted {deleted_obs:,} observations")
        LOGGER.info(f"   - Deleted {deleted_hist:,} price history entries")

        # Run VACUUM
        print("\nRunning VACUUM to reclaim disk space...")
        session.execute("VACUUM")
        LOGGER.info("Database optimized")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cleanup high value old items")
    parser.add_argument(
        "--dry-run", action="store_true", help="Show what would be deleted"
    )
    args = parser.parse_args()

    cleanup_high_value_old_items(args.dry_run)
