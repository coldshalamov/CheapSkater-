"""Health monitoring helpers for scraper anomaly detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import time
from pathlib import Path
from typing import Any


class HealthState(str, Enum):
    """Overall scraper health classification."""

    HEALTHY = "healthy"
    SUSPECT = "suspect"
    BLOCKED = "blocked"


@dataclass
class HealthMonitor:
    """Tracks anomaly counts and logs structured health events."""

    run_id: str
    log_path: Path
    zero_threshold: tuple[int, int] = (3, 6)
    http_threshold: tuple[int, int] = (2, 4)
    dom_threshold: tuple[int, int] = (2, 4)
    state: HealthState = field(init=False, default=HealthState.HEALTHY)

    def __post_init__(self) -> None:
        self.zero_streak = 0
        self.http_errors = 0
        self.dom_errors = 0
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def _log(self, event_type: str, message: str, **details: Any) -> None:
        entry = {
            "ts": time.time(),
            "run_id": self.run_id,
            "state": self.state.value,
            "event": event_type,
            "message": message,
            "details": details,
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _evaluate_state(self) -> None:
        prev = self.state
        if (
            self.zero_streak >= self.zero_threshold[1]
            or self.http_errors >= self.http_threshold[1]
            or self.dom_errors >= self.dom_threshold[1]
        ):
            self.state = HealthState.BLOCKED
        elif (
            self.zero_streak >= self.zero_threshold[0]
            or self.http_errors >= self.http_threshold[0]
            or self.dom_errors >= self.dom_threshold[0]
        ):
            self.state = HealthState.SUSPECT
        else:
            self.state = HealthState.HEALTHY

        if self.state != prev:
            self._log(
                "state_change",
                f"{prev.value} -> {self.state.value}",
                zero_streak=self.zero_streak,
                http_errors=self.http_errors,
                dom_errors=self.dom_errors,
            )

    def record_items(self, *, zip_code: str, count: int) -> None:
        """Record a successful scrape with items."""
        self.zero_streak = 0
        self.http_errors = max(0, self.http_errors - 1)
        self.dom_errors = max(0, self.dom_errors - 1)
        if self.state != HealthState.HEALTHY:
            self._log("recovered", f"Recovered on zip {zip_code}", items=count)
        self._evaluate_state()

    def record_zero_items(self, *, zip_code: str, message: str | None = None) -> None:
        self.zero_streak += 1
        self._log(
            "zero_items",
            message or f"No items returned for zip {zip_code}",
            zero_streak=self.zero_streak,
        )
        self._evaluate_state()

    def record_http_error(self, *, zip_code: str, reason: str, details: dict[str, Any] | None = None) -> None:
        self.http_errors += 1
        self._log(
            "http_error",
            reason,
            zip=zip_code,
            http_errors=self.http_errors,
            **(details or {}),
        )
        self._evaluate_state()

    def record_dom_error(self, *, zip_code: str, reason: str, details: dict[str, Any] | None = None) -> None:
        self.dom_errors += 1
        self._log(
            "dom_error",
            reason,
            zip=zip_code,
            dom_errors=self.dom_errors,
            **(details or {}),
        )
        self._evaluate_state()

    def record_browser_restart(self, *, reason: str) -> None:
        self._log("browser_restart", f"Restarted browser: {reason}")

    def record_data_anomaly(self, *, zip_code: str, detail: str, metrics: dict[str, Any]) -> None:
        self._log("data_anomaly", detail, zip=zip_code, **metrics)

    def recommended_extra_delay(self) -> float:
        if self.state == HealthState.SUSPECT:
            return 5.0
        if self.state == HealthState.BLOCKED:
            return 15.0
        return 0.0

