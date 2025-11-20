"""Centralised helpers for Playwright launch + anti-bot configuration."""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Playwright,
)

try:  # Defensive: TargetClosedError was added in later Playwright releases.
    from playwright.async_api import TargetClosedError
except Exception:  # pragma: no cover - fallback for future/beta releases
    TargetClosedError = PlaywrightError  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)

_FALSE_VALUES = {"0", "false", "no", "off"}
_INSTALL_LOCK = Lock()
_INSTALL_ATTEMPTED = False
_PLAYWRIGHT_INSTALL_HINTS = (
    "Executable doesn't exist at",
    "Please run the following command to download new browsers",
    "Looks like Playwright was just installed or updated",
)
_PERSISTENT_PROFILE_DISABLED = False


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

    # Default to headful to better mimic a real browser.
    return _as_bool(os.getenv("CHEAPSKATER_HEADLESS"), False)


def selector_validation_skipped() -> bool:
    """Return True when selector validation/preflight should be bypassed."""

    return os.getenv("CHEAPSKATER_SKIP_PREFLIGHT") == "1"


def stealth_enabled() -> bool:
    """Return True when stealth evasion scripts should be applied."""

    return _as_bool(os.getenv("CHEAPSKATER_STEALTH"), False)


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


def _persistent_profiles_disabled() -> bool:
    if _PERSISTENT_PROFILE_DISABLED:
        return True
    # Default to disabling persistent profiles to avoid lock/corruption issues.
    return _as_bool(os.getenv("CHEAPSKATER_DISABLE_PERSISTENT_PROFILE"), True)


def _user_data_dir() -> Path | None:
    if _persistent_profiles_disabled():
        return None

    raw = os.getenv("CHEAPSKATER_USER_DATA_DIR")
    # Default to a persistent profile to reuse cookies/fingerprint between runs.
    if not raw:
        raw = ".playwright-profile/chromium"
    path = Path(raw).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _clear_singleton_lock(user_dir: Path | None) -> None:
    """Remove Chromium's stale SingletonLock to avoid startup hangs."""

    if user_dir is None:
        return
    lock_file = user_dir / "SingletonLock"
    try:
        if lock_file.exists():
            lock_file.unlink()
            LOGGER.warning("Removed stale SingletonLock at %s", lock_file)
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.warning("Failed to remove SingletonLock at %s: %s", lock_file, exc)


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

    if _as_bool(os.getenv("CHEAPSKATER_MINIMAL_LAUNCH"), True):
        # Minimal settings to maximise launch reliability.
        return {
            "headless": headless_enabled(),
            # Keep args simple but deterministic; add start-maximized to ensure visibility.
            "args": [
                "--start-maximized",
                "--disable-dev-shm-usage",
                "--disable-infobars",
            ],
        }

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


def _missing_browser_binary(exc: Exception) -> bool:
    message = str(exc)
    return any(hint in message for hint in _PLAYWRIGHT_INSTALL_HINTS)


def _requires_browser_install(channel: str | None) -> str | None:
    if not channel:
        return "chromium"
    normalized = channel.strip().lower()
    if not normalized:
        return "chromium"
    if normalized == "chromium":
        return "chromium"
    return None


def _ensure_playwright_browser_installed(channel: str | None) -> bool:
    target = _requires_browser_install(channel)
    if not target:
        return False

    global _INSTALL_ATTEMPTED
    with _INSTALL_LOCK:
        if _INSTALL_ATTEMPTED:
            return False
        _INSTALL_ATTEMPTED = True

        cmd = [sys.executable, "-m", "playwright", "install", target]
        display_cmd = " ".join(shlex.quote(part) for part in cmd)
        LOGGER.warning(
            "Playwright browser binary missing; executing %s", display_cmd
        )
        try:
            subprocess.run(cmd, check=True)
        except Exception as exc:
            LOGGER.error(
                "Automatic Playwright browser installation failed: %s", exc
            )
            return False

    LOGGER.info("Playwright browser '%s' installed successfully", target)
    return True


def _disable_persistent_profile(reason: str) -> None:
    global _PERSISTENT_PROFILE_DISABLED
    if _PERSISTENT_PROFILE_DISABLED:
        return
    _PERSISTENT_PROFILE_DISABLED = True
    LOGGER.warning(
        "Disabling persistent Playwright profile for current process (%s)",
        reason,
    )


def _reset_user_data_dir(path: Path) -> bool:
    try:
        if path.exists():
            shutil.rmtree(path)
    except Exception as exc:
        LOGGER.error("Unable to remove Playwright profile %s: %s", path, exc)
        return False

    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        LOGGER.error("Unable to recreate Playwright profile %s: %s", path, exc)
        return False

    return True


def _should_reset_profile(exc: Exception) -> bool:
    message = str(exc)
    if isinstance(exc, TargetClosedError):
        return True
    return any(
        hint in message
        for hint in (
            "Target page, context or browser has been closed",
            "browser has been closed",
            "context has been closed",
        )
    )


async def launch_browser(playwright: Playwright) -> tuple[Browser, BrowserContext | None]:
    """Launch Chromium according to env overrides. Returns (browser, persistent_context)."""

    user_dir = _user_data_dir()
    kwargs = launch_kwargs()
    return await _launch_with_retry(playwright, user_dir, kwargs)


async def _perform_launch(
    playwright: Playwright, user_dir: Path | None, kwargs: dict[str, Any]
) -> tuple[Browser, BrowserContext | None]:
    _clear_singleton_lock(user_dir)
    LOGGER.error(  # force visibility
        "Launching Chromium | headless=%s | user_dir=%s | channel=%s | args=%s",
        kwargs.get("headless"),
        user_dir,
        kwargs.get("channel"),
        kwargs.get("args"),
    )
    if user_dir is not None:
        context = await playwright.chromium.launch_persistent_context(
            str(user_dir), **kwargs
        )
        return context.browser, context

    browser = await playwright.chromium.launch(**kwargs)
    return browser, None


async def _launch_with_retry(
    playwright: Playwright,
    user_dir: Path | None,
    kwargs: dict[str, Any],
    *,
    allow_install_retry: bool = True,
    allow_profile_reset: bool = True,
    allow_ephemeral_fallback: bool = True,
    allow_minimal_fallback: bool = True,
) -> tuple[Browser, BrowserContext | None]:
    try:
        return await _perform_launch(playwright, user_dir, kwargs)
    except Exception as exc:
        LOGGER.error(
            "Playwright launch attempt failed | user_dir=%s | kwargs=%s | error=%s",
            user_dir,
            kwargs,
            exc,
        )
        if allow_install_retry and _missing_browser_binary(exc):
            if _ensure_playwright_browser_installed(kwargs.get("channel")):
                LOGGER.info(
                    "Retrying Playwright launch after installing browsers"
                )
                return await _launch_with_retry(
                    playwright,
                    user_dir,
                    kwargs,
                    allow_install_retry=False,
                    allow_profile_reset=allow_profile_reset,
                    allow_ephemeral_fallback=allow_ephemeral_fallback,
                    allow_minimal_fallback=allow_minimal_fallback,
                )

        if user_dir is not None and allow_profile_reset and _should_reset_profile(exc):
            if _reset_user_data_dir(user_dir):
                LOGGER.warning(
                    "Playwright persistent profile at %s reset after crash",
                    user_dir,
                )
                return await _launch_with_retry(
                    playwright,
                    user_dir,
                    kwargs,
                    allow_install_retry=False,
                    allow_profile_reset=False,
                    allow_ephemeral_fallback=allow_ephemeral_fallback,
                    allow_minimal_fallback=allow_minimal_fallback,
                )

        if user_dir is not None and allow_ephemeral_fallback:
            _disable_persistent_profile(str(exc))
            LOGGER.warning(
                "Falling back to non-persistent Chromium profile after launch failure"
            )
            return await _launch_with_retry(
                playwright,
                None,
                kwargs,
                allow_install_retry=False,
                allow_profile_reset=False,
                allow_ephemeral_fallback=False,
                allow_minimal_fallback=allow_minimal_fallback,
            )

        if allow_minimal_fallback:
            LOGGER.warning(
                "Playwright launch failed with configured kwargs; retrying with minimal defaults (headless, no channel, no args)"
            )
            minimal_kwargs = {"headless": True}
            try:
                return await _launch_with_retry(
                    playwright,
                    None,
                    minimal_kwargs,
                    allow_install_retry=False,
                    allow_profile_reset=False,
                    allow_ephemeral_fallback=False,
                    allow_minimal_fallback=False,
                )
            except Exception as inner_exc:
                LOGGER.error("Minimal Playwright launch fallback failed: %s", inner_exc)

        raise


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
