"""Centralised helpers for Playwright launch + anti-bot configuration."""

from __future__ import annotations

import logging
import os
import random
import shlex
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.async_api import Browser, BrowserContext, Playwright

LOGGER = logging.getLogger(__name__)

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

    # Default to headful for stability; override via env if needed.
    return _as_bool(os.getenv("CHEAPSKATER_HEADLESS"), False)


def selector_validation_skipped() -> bool:
    """Return True when selector validation/preflight should be bypassed."""

    return os.getenv("CHEAPSKATER_SKIP_PREFLIGHT") == "1"


def stealth_enabled() -> bool:
    """Return True when stealth evasion scripts should be applied."""

    return _as_bool(os.getenv("CHEAPSKATER_ENABLE_STEALTH"), False)


@lru_cache(maxsize=1)
def _stealth_instance():
    try:
        from playwright_stealth import Stealth
    except Exception:
        return None
    try:
        return Stealth()
    except Exception:
        return None


def apply_stealth(playwright: Playwright) -> None:
    """Hook the provided Playwright object with stealth evasions when available."""

    if not stealth_enabled():
        return

    stealth = _stealth_instance()
    if stealth is None:
        return

    try:
        stealth.apply(playwright)
    except Exception:
        LOGGER.debug("Stealth apply() failed; continuing without extra patches")


def _user_data_dir() -> Path | None:
    raw = os.getenv("CHEAPSKATER_USER_DATA_DIR")
    # Default to no persistent profile unless explicitly provided.
    if raw is None:
        return None

    lowered = raw.strip().lower()
    if lowered in {"none", "off", "disable", "disabled", ""}:
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
    ]
    try:
        width, height = random.choice([(1280, 720), (1366, 768), (1440, 900), (1600, 900)])
        args.append(f"--window-size={width},{height}")
    except Exception:
        args.append("--window-size=1440,900")
    extra_args = os.getenv("CHEAPSKATER_CHROMIUM_ARGS")
    if extra_args:
        args.extend(shlex.split(extra_args))

    kwargs: dict[str, Any] = {
        "headless": headless_enabled(),
        "args": args,
    }

    # Use provided channel only if explicitly set.
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

    cdp_url = os.getenv("CHEAPSKATER_CDP_URL")
    if cdp_url:
        try:
            browser = await playwright.chromium.connect_over_cdp(cdp_url.strip())
            page = None
            # Prefer existing page/context; as a fallback create a single page.
            if browser.contexts and browser.contexts[0].pages:
                page = browser.contexts[0].pages[0]
            elif browser.contexts:
                page = await browser.contexts[0].new_page()
            else:
                page = await browser.new_page()

            context: BrowserContext | None = page.context if page is not None else None
            if context is None:
                raise RuntimeError("CDP attached but no open browser context/page was found.")

            try:
                setattr(browser, "_cheapskater_external", True)
                if context is not None:
                    setattr(context, "_cheapskater_external", True)
                if page is not None:
                    setattr(page, "_cheapskater_external", True)
            except Exception:
                pass
            return browser, context
        except Exception as exc:
            # CDP is required when provided; surface as fatal so the user can reopen Chrome.
            raise RuntimeError(f"CDP attach failed: {exc}") from exc

    kwargs = launch_kwargs()
    channel = kwargs.pop("channel", None)
    user_data_dir = _user_data_dir()

    if user_data_dir is not None:
        try:
            if channel:
                context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    channel=channel,
                    **kwargs,
                )
            else:
                context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    **kwargs,
                )
            return context.browser, context
        except Exception as exc:
            LOGGER.warning("Persistent context launch failed, falling back: %s", exc)

    if channel:
        try:
            browser = await playwright.chromium.launch(channel=channel, **kwargs)
            return browser, None
        except Exception as exc:
            LOGGER.warning("Channel launch failed (%s); retrying default Chromium", exc)

    browser = await playwright.chromium.launch(**kwargs)
    return browser, None



async def close_browser(browser: Browser | None, context: BrowserContext | None) -> None:
    """Close the provided browser/context pair without raising."""

    if context is not None:
        if getattr(context, "_cheapskater_external", False):
            return
        try:
            await context.close()
        except Exception:
            pass
        return

    if browser is not None:
        if getattr(browser, "_cheapskater_external", False):
            return
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
