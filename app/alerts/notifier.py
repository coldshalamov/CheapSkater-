"""Alert notification helper utilities."""

from __future__ import annotations

import html
import os
from typing import Any

import requests

from app.logging_config import get_logger
from app.storage.models_sql import Item, Observation


LOGGER = get_logger(__name__)


class Notifier:
    """Dispatch alert notifications to configured providers."""

    _noop_logged = False

    def __init__(self) -> None:
        self._mode: str = "noop"
        self._telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self._telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self._sendgrid_key = os.getenv("SENDGRID_API_KEY")
        self._sendgrid_to = os.getenv("SENDGRID_TO")
        self._sendgrid_from = os.getenv("SENDGRID_FROM")

        if self._telegram_token and self._telegram_chat_id:
            self._mode = "telegram"
            LOGGER.info("Notifier configured for Telegram alerts")
        elif self._sendgrid_key and self._sendgrid_to and self._sendgrid_from:
            self._mode = "sendgrid"
            LOGGER.info("Notifier configured for SendGrid alerts")
        else:
            if not Notifier._noop_logged:
                LOGGER.warning(
                    "No alert transport configured; alerts will be logged only"
                )
                Notifier._noop_logged = True

    def notify_new_clearance(
        self, item: Item, obs: Observation, pct_off: float | None
    ) -> None:
        """Notify about a new clearance item."""

        title = self._shorten(item.title)
        pct_text = self._format_pct(pct_off)
        price = self._format_price(obs.price)
        was = self._format_price(obs.price_was)
        zip_code = getattr(obs, "zip", None)
        store_id = getattr(obs, "store_id", None) or obs.store_id
        url = item.product_url

        lines = [f"New clearance: {title}"]
        if price:
            lines.append(f"Now: {price}")
        if was:
            lines.append(f"Was: {was}")
        if pct_text:
            lines.append(f"% off: {pct_text}")
        if store_id:
            lines.append(f"Store: {store_id}")
        if zip_code:
            lines.append(f"ZIP: {zip_code}")
        lines.append(url)

        subject = f"New clearance: {title}"
        self._dispatch(subject, lines)

    def notify_price_drop(
        self,
        item: Item,
        old_obs: Observation,
        new_obs: Observation,
        pct_off: float,
    ) -> None:
        """Notify about a price drop on an existing item."""

        title = self._shorten(item.title)
        pct_text = self._format_pct(pct_off)
        price_new = self._format_price(new_obs.price)
        price_old = self._format_price(old_obs.price)
        was = self._format_price(new_obs.price_was)
        zip_code = getattr(new_obs, "zip", None)
        store_id = getattr(new_obs, "store_id", None) or new_obs.store_id
        url = item.product_url

        lines = [f"Price drop: {title}"]
        if price_new:
            lines.append(f"Now: {price_new}")
        if price_old:
            lines.append(f"Was: {price_old}")
        elif was:
            lines.append(f"Was: {was}")
        if pct_text:
            lines.append(f"Drop: {pct_text}")
        if store_id:
            lines.append(f"Store: {store_id}")
        if zip_code:
            lines.append(f"ZIP: {zip_code}")
        lines.append(url)

        subject = f"Price drop: {title}"
        self._dispatch(subject, lines)

    def _dispatch(self, subject: str, lines: list[str]) -> None:
        if self._mode == "noop":
            LOGGER.debug("Notifier noop: %s", " | ".join(lines))
            return

        text = "\n".join(lines)
        if len(text) > 400:
            text = f"{text[:397]}..."

        if self._mode == "telegram":
            self._send_telegram(text)
        elif self._mode == "sendgrid":
            self._send_sendgrid(subject, lines)

    def _send_telegram(self, text: str) -> None:
        if not self._telegram_token or not self._telegram_chat_id:
            return
        url = f"https://api.telegram.org/bot{self._telegram_token}/sendMessage"
        payload = {
            "chat_id": self._telegram_chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        try:
            response = requests.post(url, json=payload, timeout=8)
        except Exception as exc:  # pragma: no cover - network failure
            LOGGER.error("Failed to send Telegram alert: %s", exc)
            return
        if response.status_code != 200:
            LOGGER.warning(
                "Telegram responded with %s: %s", response.status_code, response.text
            )

    def _send_sendgrid(self, subject: str, lines: list[str]) -> None:
        if not (self._sendgrid_key and self._sendgrid_to and self._sendgrid_from):
            return

        html_lines = [f"<p>{html.escape(line)}</p>" for line in lines[:-1]]
        link = html.escape(lines[-1]) if lines else ""
        html_body = "".join(html_lines) + f"<p><a href=\"{link}\">{link}</a></p>"
        payload: dict[str, Any] = {
            "from": {"email": self._sendgrid_from},
            "personalizations": [
                {
                    "to": [{"email": self._sendgrid_to}],
                    "subject": subject,
                }
            ],
            "content": [
                {
                    "type": "text/html",
                    "value": html_body,
                }
            ],
        }
        headers = {
            "Authorization": f"Bearer {self._sendgrid_key}",
        }
        try:
            response = requests.post(
                "https://api.sendgrid.com/v3/mail/send",
                json=payload,
                headers=headers,
                timeout=8,
            )
        except Exception as exc:  # pragma: no cover - network failure
            LOGGER.error("Failed to send SendGrid alert: %s", exc)
            return
        if not (200 <= response.status_code < 300):
            LOGGER.warning(
                "SendGrid responded with %s: %s",
                response.status_code,
                response.text,
            )

    @staticmethod
    def _shorten(text: str, limit: int = 70) -> str:
        if len(text) <= limit:
            return text
        return f"{text[: limit - 1]}…"

    @staticmethod
    def _format_price(value: float | None) -> str | None:
        if value is None:
            return None
        return f"${value:,.2f}"

    @staticmethod
    def _format_pct(value: float | None) -> str | None:
        if value is None:
            return None
        return f"{value * 100:.1f}%"
