"""Monitoring helpers for CheapSkater reliability features."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

try:  # psutil is optional at import time
    import psutil  # type: ignore
except Exception:  # pragma: no cover - psutil import guard
    psutil = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception:
        return {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class MetricsEmitter:
    """Append-only JSONL metrics plus a rolling summary snapshot."""

    log_path: Path
    summary_path: Path
    enabled: bool = True
    _summary: dict[str, Any] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if not self.enabled:
            return
        self._summary = _read_json(self.summary_path) or {
            "zip_started": 0,
            "zip_finished": 0,
            "zip_errors": {},
            "rows_collected": 0,
            "last_event": None,
        }

    def emit(self, event: str, **fields: Any) -> None:
        if not self.enabled:
            return
        entry = {"ts": _now().isoformat(), "event": event}
        entry.update(fields)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            return
        self._update_summary(entry)

    def _update_summary(self, entry: dict[str, Any]) -> None:
        event = entry.get("event")
        if event == "zip_started":
            self._summary["zip_started"] = int(self._summary.get("zip_started", 0)) + 1
        elif event == "zip_finished":
            self._summary["zip_finished"] = int(self._summary.get("zip_finished", 0)) + 1
            rows = int(entry.get("rows", 0) or 0)
            self._summary["rows_collected"] = int(self._summary.get("rows_collected", 0)) + max(rows, 0)
        elif event == "zip_error":
            reason = entry.get("reason") or "unknown"
            errors = dict(self._summary.get("zip_errors") or {})
            errors[reason] = int(errors.get(reason, 0)) + 1
            self._summary["zip_errors"] = errors
        self._summary["last_event"] = entry.get("ts")
        try:
            _write_json(self.summary_path, self._summary)
        except Exception:
            return

    def summary(self) -> dict[str, Any]:
        return dict(self._summary)


@dataclass
class ZipProgressTracker:
    """Tracks ZIP completion timestamps and queue ordering."""

    cursor_path: Path
    history_path: Path
    watchdog_minutes: float = 0.0
    _history: dict[str, str] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        self._history = _read_json(self.history_path) or {}

    def record_success(self, zip_code: str, timestamp: datetime) -> None:
        self._history[zip_code] = timestamp.isoformat()
        try:
            _write_json(self.history_path, self._history)
        except Exception:
            pass

    def load_history(self) -> dict[str, datetime]:
        parsed: dict[str, datetime] = {}
        for zip_code, iso_ts in self._history.items():
            try:
                parsed[zip_code] = datetime.fromisoformat(iso_ts)
            except Exception:
                continue
        return parsed

    def interleave(self, zips: list[str], state_resolver: Callable[[str | None], str]) -> list[str]:
        history = self.load_history()
        def _sort_key(zip_code: str) -> tuple[int, float]:
            ts = history.get(zip_code)
            age = ts.timestamp() if ts else 0.0
            return (0 if ts else 1, age)

        wa = sorted([z for z in zips if state_resolver(z) == "WA"], key=_sort_key)
        or_zips = sorted([z for z in zips if state_resolver(z) == "OR"], key=_sort_key)
        unknown = sorted([z for z in zips if state_resolver(z) not in {"WA", "OR"}], key=_sort_key)

        interleaved: list[str] = []
        while wa or or_zips:
            if wa:
                interleaved.append(wa.pop(0))
            if or_zips:
                interleaved.append(or_zips.pop(0))
        interleaved.extend(unknown)
        seen = set()
        ordered: list[str] = []
        for zip_code in interleaved:
            if zip_code not in seen:
                ordered.append(zip_code)
                seen.add(zip_code)
        for zip_code in zips:
            if zip_code not in seen:
                ordered.append(zip_code)
        return ordered

    def last_completion(self) -> datetime | None:
        data = _read_json(self.cursor_path)
        stamp = data.get("timestamp") if isinstance(data, dict) else None
        if not stamp:
            return None
        try:
            return datetime.fromisoformat(stamp)
        except Exception:
            return None

    def watchdog_triggered(self) -> tuple[bool, float]:
        if self.watchdog_minutes <= 0:
            return False, 0.0
        last = self.last_completion()
        if last is None:
            return True, float("inf")
        delta = (_now() - last).total_seconds() / 60.0
        return delta >= self.watchdog_minutes, delta


@dataclass
class DataConsistencyTracker:
    """Maintains recent per-ZIP row counts to surface silent failures."""

    path: Path
    history_length: int = 10
    zero_threshold: int = 3
    _history: dict[str, list[int]] = field(default_factory=dict, init=False)
    _dirty: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        raw = _read_json(self.path)
        history = raw.get("history") if isinstance(raw, dict) else None
        if isinstance(history, dict):
            parsed: dict[str, list[int]] = {}
            for key, values in history.items():
                if isinstance(values, list):
                    parsed[key] = [int(v) for v in values[-self.history_length :]]
            self._history = parsed
        else:
            self._history = {}

    def record(self, zip_code: str, row_count: int) -> None:
        if zip_code not in self._history:
            self._history[zip_code] = []
        self._history[zip_code].append(int(row_count))
        if len(self._history[zip_code]) > self.history_length:
            self._history[zip_code] = self._history[zip_code][-self.history_length :]
        self._dirty = True

    def save(self) -> None:
        if not self._dirty:
            return
        payload = {"history": self._history}
        try:
            _write_json(self.path, payload)
        finally:
            self._dirty = False

    def detect_zero_streaks(self) -> list[dict[str, Any]]:
        anomalies: list[dict[str, Any]] = []
        for zip_code, counts in self._history.items():
            streak = 0
            for value in reversed(counts):
                if value == 0:
                    streak += 1
                else:
                    break
            if streak >= self.zero_threshold:
                anomalies.append({"zip": zip_code, "zero_streak": streak})
        return anomalies


@dataclass
class MemoryWatchdog:
    """Terminates the process when RSS exceeds the configured limit."""

    limit_mb: float
    interval_seconds: float
    logger: Any
    _task: asyncio.Task[None] | None = field(default=None, init=False)

    def start(self) -> None:
        if self.limit_mb <= 0:
            return
        if psutil is None:
            self.logger.warning("Memory watchdog enabled but psutil is missing; skipping.")
            return
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._monitor(), name="memory-watchdog")

    async def _monitor(self) -> None:
        assert psutil is not None
        process = psutil.Process(os.getpid())
        limit_bytes = self.limit_mb * 1024 * 1024
        try:
            while True:
                await asyncio.sleep(max(1.0, self.interval_seconds))
                rss = process.memory_info().rss
                if rss >= limit_bytes:
                    self.logger.error(
                        "Memory watchdog triggered | rss_mb=%.1f limit_mb=%.1f",
                        rss / (1024 * 1024),
                        self.limit_mb,
                    )
                    os._exit(1)
        except asyncio.CancelledError:  # pragma: no cover - cancellation path
            return

    def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        self._task = None
