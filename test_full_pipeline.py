#!/usr/bin/env python3
"""End-to-end pipeline verification for CheapSkater."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

TIMEOUT = 300
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
TEST_LOG = LOG_DIR / "test_full_pipeline.log"


def _log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with TEST_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")
    print(message)


def run_command(description: str, *args: str, timeout: int = TIMEOUT) -> subprocess.CompletedProcess:
    command_str = " ".join([sys.executable, *args])
    _log(f"Running: {description} -> {command_str}")
    result = subprocess.run(
        [sys.executable, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
    )
    with TEST_LOG.open("a", encoding="utf-8") as handle:
        handle.write(result.stdout)
    if result.returncode != 0:
        _log(f"Command failed ({description}):\n{result.stdout}")
        raise RuntimeError(description)
    return result


def ensure_catalogs() -> None:
    catalog = Path("catalog/building_materials.lowes.yml")
    stores = Path("catalog/wa_or_stores.yml")
    if not catalog.exists():
        run_command("discover categories", "-m", "app.main", "--discover-categories")
    if not stores.exists():
        run_command("discover stores", "-m", "app.main", "--discover-stores")


def run_probe() -> None:
    result = run_command(
        "probe",
        "-m",
        "app.main",
        "--probe",
        "--zips",
        "98101",
    )
    parsed = None
    for line in reversed(result.stdout.splitlines()):
        candidate = line.strip()
        if candidate.startswith("{") and candidate.endswith("}"):
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"Probe did not return valid JSON: {exc}") from exc
            break
    if parsed is None:
        raise RuntimeError("Probe output did not include JSON payload")
    _log("Probe JSON: " + json.dumps(parsed))


def run_scrape() -> None:
    run_command(
        "one-time scrape",
        "-m",
        "app.main",
        "--once",
        "--zips",
        "98101,98102",
        "--categories",
        "Roof|Drywall",
        "--concurrency",
        "2",
    )


def check_outputs() -> None:
    csv_path = Path("outputs/orwa_items.csv")
    sqlite_path = Path("orwa_lowes.sqlite")
    if not csv_path.exists():
        raise RuntimeError("CSV export not found after scrape")
    if not sqlite_path.exists():
        raise RuntimeError("SQLite database not found after scrape")


def query_dashboard() -> None:
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    log_handle = TEST_LOG.open("a", encoding="utf-8")
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.dashboard:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        stdout=log_handle,
        stderr=log_handle,
        text=True,
        env=env,
    )
    try:
        start = time.time()
        while time.time() - start < 30:
            try:
                response = requests.get("http://127.0.0.1:8000/api/stats", timeout=2)
                if response.ok:
                    _log("Dashboard stats: " + json.dumps(response.json()))
                    return
            except requests.RequestException:
                time.sleep(1)
        raise RuntimeError("Dashboard API did not respond within timeout")
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
        log_handle.close()


def main() -> int:
    start = time.time()
    TEST_LOG.write_text("", encoding="utf-8")
    try:
        ensure_catalogs()
        run_probe()
        run_scrape()
        check_outputs()
        query_dashboard()
        elapsed = time.time() - start
        if elapsed > TIMEOUT:
            raise RuntimeError("Full pipeline exceeded 5-minute limit")
        _log(f"Full pipeline completed in {elapsed:.2f} seconds")
        return 0
    except Exception as exc:  # pragma: no cover - integration script
        _log(f"Pipeline test failed: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
