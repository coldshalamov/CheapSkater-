"""Alert notification helper utilities."""

from __future__ import annotations

import html
import os
from typing import Iterable

import requests

from app.logging_config import get_logger
from app.storage.models_sql import Observation

LOGGER = get_logger(__name__)


class Notifier:
    """Send alerts via Telegram or SendGrid when credentials are present."""

    def __init__(self) -> None:
        self._telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self._telegram_chat = os.getenv("TELEGRAM_CHAT_ID")
        self._sendgrid_key = os.getenv("SENDGRID_API_KEY")
        self._sendgrid_to = os.getenv("SENDGRID_TO")
        self._sendgrid_from = os.getenv("SENDGRID_FROM")

    def notify_new_clearance(self, obs: Observation) -> None:
        """Send a clearance alert when transport is configured."""

        message = self._build_lines("New clearance", obs)
        self._dispatch(f"New clearance: {obs.title}", message)

    def notify_price_drop(self, obs: Observation, last_obs: Observation) -> None:
        """Send a price-drop alert when transport is configured."""

        lines = self._build_lines("Price drop", obs, last_obs=last_obs)
        self._dispatch(f"Price drop: {obs.title}", lines)

    def _build_lines(
        self,
        prefix: str,
        obs: Observation,
        *,
        last_obs: Observation | None = None,
    ) -> list[str]:
        now_price = self._format_price(obs.price)
        was_price = self._format_price(obs.price_was)
        previous_price = self._format_price(last_obs.price) if last_obs else None
        pct_off = self._format_pct(obs.pct_off)
        lines = [f"{prefix}: {obs.title}"]
        if now_price:
            lines.append(f"Now: {now_price}")
        if previous_price:
            lines.append(f"Prev: {previous_price}")
        elif was_price:
            lines.append(f"Was: {was_price}")
        if pct_off:
            lines.append(f"% off: {pct_off}")
        if obs.store_name:
            lines.append(f"Store: {obs.store_name}")
        if obs.zip:
            lines.append(f"ZIP: {obs.zip}")
        lines.append(f"SKU: {obs.sku}")
        lines.append(obs.product_url)
        return lines

    def _dispatch(self, subject: str, lines: list[str]) -> None:
        if self._telegram_token and self._telegram_chat:
            self._send_telegram(lines)
        elif self._sendgrid_key and self._sendgrid_to and self._sendgrid_from:
            self._send_sendgrid(subject, lines)
        else:
            LOGGER.debug("Alert (noop): %s", " | ".join(lines))

    def _send_telegram(self, lines: Iterable[str]) -> None:
        url = f"https://api.telegram.org/bot{self._telegram_token}/sendMessage"
        payload = {
            "chat_id": self._telegram_chat,
            "text": "\n".join(lines),
            "disable_web_page_preview": True,
        }
        try:
            response = requests.post(url, json=payload, timeout=8)
            if response.status_code >= 400:
                LOGGER.warning("Telegram responded with %s: %s", response.status_code, response.text)
        except Exception as exc:  # pragma: no cover - network failures
            LOGGER.error("Failed to send Telegram alert: %s", exc)

    def _send_sendgrid(self, subject: str, lines: list[str]) -> None:
        body = "".join(f"<p>{html.escape(line)}</p>" for line in lines[:-1])
        link = html.escape(lines[-1])
        body += f"<p><a href=\"{link}\">{link}</a></p>"
        payload = {
            "from": {"email": self._sendgrid_from},
            "personalizations": [{"to": [{"email": self._sendgrid_to}], "subject": subject}],
            "content": [{"type": "text/html", "value": body}],
        }
        headers = {"Authorization": f"Bearer {self._sendgrid_key}"}
        try:
            response = requests.post("https://api.sendgrid.com/v3/mail/send", json=payload, headers=headers, timeout=8)
            if response.status_code >= 300:
                LOGGER.warning("SendGrid responded with %s: %s", response.status_code, response.text)
        except Exception as exc:  # pragma: no cover - network failures
            LOGGER.error("Failed to send SendGrid alert: %s", exc)

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
