"""Disk-backed cache for last-known ZIP scrape rows."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _zip_path(base_dir: Path, zip_code: str) -> Path:
    safe = "".join(ch for ch in zip_code if ch.isdigit())
    return base_dir / f"{safe or 'unknown'}.json"


def store_snapshot(base_dir: Path, zip_code: str, rows: Iterable[dict[str, Any]]) -> None:
    payload = {
        "zip": zip_code,
        "ts": _now().isoformat(),
        "rows": list(rows),
    }
    target = _zip_path(base_dir, zip_code)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def load_snapshot(base_dir: Path, zip_code: str, ttl_minutes: float) -> list[dict[str, Any]] | None:
    target = _zip_path(base_dir, zip_code)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except Exception:
        return None
    ts_text = payload.get("ts")
    if not isinstance(ts_text, str):
        return None
    try:
        stamp = datetime.fromisoformat(ts_text)
    except Exception:
        return None
    if ttl_minutes > 0:
        delta = _now() - stamp
        if delta > timedelta(minutes=ttl_minutes):
            return None
    rows = payload.get("rows")
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return None
