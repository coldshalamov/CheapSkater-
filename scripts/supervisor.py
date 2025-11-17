"""Simple supervisor that restarts CheapSkater when it crashes."""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Supervise a CheapSkater command and restart on failure.")
    parser.add_argument(
        "--max-restarts",
        type=int,
        default=5,
        help="Maximum number of automatic restarts for non-zero exits (default: 5).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=5.0,
        help="Initial delay in seconds before restarting the child process (default: 5).",
    )
    parser.add_argument(
        "--max-delay",
        type=float,
        default=120.0,
        help="Upper bound for the restart delay when exponential backoff is applied (default: 120).",
    )
    parser.add_argument(
        "--backoff",
        type=float,
        default=1.5,
        help="Multiplier applied to the restart delay after each failure (default: 1.5).",
    )
    parser.add_argument(
        "--always-restart",
        action="store_true",
        help="Restart even after a clean exit instead of stopping.",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to run (defaults to `python -m app.main`).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command:
        command = args.command
    else:
        command = [sys.executable, "-m", "app.main"]

    restarts = 0
    delay = max(0.0, args.delay)

    while True:
        print(f"[supervisor] starting: {' '.join(shlex.quote(part) for part in command)}")
        result = subprocess.run(command)
        exit_code = result.returncode
        print(f"[supervisor] process exited with code {exit_code}")

        if exit_code == 0 and not args.always_restart:
            return 0

        restarts += 1
        if args.max_restarts and restarts > args.max_restarts:
            print(f"[supervisor] giving up after {restarts-1} restarts")
            return exit_code or 1

        print(f"[supervisor] restart #{restarts} in {delay:.1f}s")
        time.sleep(delay)
        delay = min(delay * args.backoff, args.max_delay)


if __name__ == "__main__":
    raise SystemExit(main())
