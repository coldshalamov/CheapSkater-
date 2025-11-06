"""Command-line interface entry point for the CheapSkater application."""

from __future__ import annotations

import argparse
from typing import List

from .logging_config import get_logger


LOGGER = get_logger(__name__)


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the application."""
    parser = argparse.ArgumentParser(description="Run the CheapSkater price monitoring pipeline.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run the pipeline a single time instead of on a schedule.",
    )
    parser.add_argument(
        "--retailer",
        choices=["lowes", "homedepot"],
        default="lowes",
        help="Retailer to target for scraping.",
    )
    parser.add_argument(
        "--zips",
        type=str,
        help="Comma-separated list of ZIP codes to override configuration values.",
    )
    parser.add_argument(
        "--categories",
        type=str,
        help="Comma-separated list of category names to override configuration values.",
    )

    args = parser.parse_args(argv)

    if args.zips:
        args.zips = [zip_code.strip() for zip_code in args.zips.split(",") if zip_code.strip()]
    else:
        args.zips = []

    if args.categories:
        args.categories = [cat.strip() for cat in args.categories.split(",") if cat.strip()]
    else:
        args.categories = []

    return args


def main() -> None:
    """Entry point for command-line execution."""
    args = parse_args()
    LOGGER.info(
        "Parsed arguments: once=%s retailer=%s zips=%s categories=%s",
        args.once, args.retailer, args.zips, args.categories
    )
    print(args)


if __name__ == "__main__":
    main()
