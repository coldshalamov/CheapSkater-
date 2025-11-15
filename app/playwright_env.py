"""Centralised helpers for Playwright launch + anti-bot configuration."""

from __future__ import annotations

import os
import shlex
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import Browser, BrowserContext, Playwright

_FALSE_VALUES = {"0", "false", "no", "off"}


def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in _FALSE_VALUES


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except ValueError:
        return default


@lru_cache(maxsize=1)
def headless_enabled() -> bool:
    """Return True if Playwright should run in headless mode."""

    return _as_bool(os.getenv("CHEAPSKATER_HEADLESS"), True)


def selector_validation_skipped() -> bool:
    """Return True when selector validation/preflight should be bypassed."""

    return os.getenv("CHEAPSKATER_SKIP_PREFLIGHT") == "1"


def stealth_enabled() -> bool:
    """Return True when stealth evasion scripts should be applied."""

    return _as_bool(os.getenv("CHEAPSKATER_STEALTH"), True)


@lru_cache(maxsize=1)
def _stealth_instance():
    if not stealth_enabled():
        return None
    try:
        from playwright_stealth import Stealth
    except Exception:
        return None

    lang_env = os.getenv("CHEAPSKATER_LANGS") or "en-US,en"
    langs = tuple(
        entry.strip()
        for entry in lang_env.split(",")
        if entry.strip()
    ) or ("en-US", "en")

    return Stealth(
        navigator_languages_override=langs[:2],
        navigator_platform_override=os.getenv("CHEAPSKATER_PLATFORM", "Win32"),
        navigator_user_agent_override=os.getenv("CHEAPSKATER_STEALTH_UA") or os.getenv("USER_AGENT"),
        navigator_vendor_override=os.getenv("CHEAPSKATER_VENDOR", "Google Inc."),
    )


def apply_stealth(playwright: Playwright) -> None:
    """Hook the provided Playwright object with stealth evasions when available."""

    instance = _stealth_instance()
    if instance is None:
        return
    try:
        instance.hook_playwright_context(playwright)
    except Exception:
        # Best-effort; fall back silently if Playwright internals change.
        pass


def _user_data_dir() -> Path | None:
    raw = os.getenv("CHEAPSKATER_USER_DATA_DIR")
    if not raw:
        return None
    path = Path(raw).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def persistent_profile_enabled() -> bool:
    """Return True when a persistent Chromium profile should be reused."""

    return _user_data_dir() is not None


def _proxy_config() -> dict[str, str] | None:
    raw = os.getenv("CHEAPSKATER_PROXY")
    if not raw:
        return None
    parsed = urlparse(raw)
    if not parsed.scheme:
        return {"server": f"http://{raw}"}
    return {"server": raw}


def slow_mo_ms() -> int | None:
    value = _env_int("CHEAPSKATER_SLOW_MO_MS", 0)
    return value if value > 0 else None


def launch_kwargs() -> dict[str, Any]:
    """Return kwargs passed to chromium.launch / launch_persistent_context."""

    args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-infobars",
        "--lang=en-US",
        "--no-default-browser-check",
        "--start-maximized",
        "--window-size=1440,960",
    ]
    extra_args = os.getenv("CHEAPSKATER_CHROMIUM_ARGS")
    if extra_args:
        args.extend(shlex.split(extra_args))

    kwargs: dict[str, Any] = {
        "headless": headless_enabled(),
        "args": args,
    }

    channel = os.getenv("CHEAPSKATER_BROWSER_CHANNEL")
    if channel:
        kwargs["channel"] = channel

    proxy = _proxy_config()
    if proxy:
        kwargs["proxy"] = proxy

    slow_mo = slow_mo_ms()
    if slow_mo:
        kwargs["slow_mo"] = slow_mo

    if _as_bool(os.getenv("CHEAPSKATER_IGNORE_HTTPS_ERRORS"), False):
        kwargs["ignore_https_errors"] = True

    return kwargs


async def launch_browser(playwright: Playwright) -> tuple[Browser, BrowserContext | None]:
    """Launch Chromium according to env overrides. Returns (browser, persistent_context)."""

    user_dir = _user_data_dir()
    kwargs = launch_kwargs()
    if user_dir is not None:
        context = await playwright.chromium.launch_persistent_context(str(user_dir), **kwargs)
        return context.browser, context

    browser = await playwright.chromium.launch(**kwargs)
    return browser, None


async def close_browser(browser: Browser | None, context: BrowserContext | None) -> None:
    """Close the provided browser/context pair without raising."""

    if context is not None:
        try:
            await context.close()
        except Exception:
            pass
        return

    if browser is not None:
        try:
            await browser.close()
        except Exception:
            pass


def apply_wait_policy(min_ms: int, max_ms: int) -> tuple[int, int]:
    """Apply global wait overrides + multiplier for human_wait() calls."""

    min_override = _env_int("CHEAPSKATER_WAIT_MIN_MS", min_ms)
    max_override = _env_int("CHEAPSKATER_WAIT_MAX_MS", max_ms)
    multiplier = max(_env_float("CHEAPSKATER_WAIT_MULTIPLIER", 1.0), 0.1)

    scaled_min = int(min_override * multiplier)
    scaled_max = int(max_override * multiplier)
    if scaled_max < scaled_min:
        scaled_max = scaled_min
    return scaled_min, scaled_max


def category_delay_bounds() -> tuple[int, int]:
    """Delay between category fetches."""

    min_ms = _env_int("CHEAPSKATER_CATEGORY_DELAY_MIN_MS", 1800)
    max_ms = _env_int("CHEAPSKATER_CATEGORY_DELAY_MAX_MS", 4200)
    if max_ms < 0:
        max_ms = 0
    if min_ms < 0:
        min_ms = 0
    if max_ms < min_ms:
        max_ms = min_ms
    return min_ms, max_ms


def zip_delay_bounds() -> tuple[int, int]:
    """Delay after processing a ZIP."""

    min_ms = _env_int("CHEAPSKATER_ZIP_DELAY_MIN_MS", 5000)
    max_ms = _env_int("CHEAPSKATER_ZIP_DELAY_MAX_MS", 15000)
    if max_ms < 0:
        max_ms = 0
    if min_ms < 0:
        min_ms = 0
    if max_ms < min_ms:
        max_ms = min_ms
    return min_ms, max_ms


def mouse_jitter_enabled() -> bool:
    """Return True when synthetic mouse movements should be emitted."""

    return _as_bool(os.getenv("CHEAPSKATER_MOUSE_JITTER"), True)
