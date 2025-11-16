"""Lightweight signed-cookie session middleware without external deps."""

from __future__ import annotations

import json
import time
import hmac
import hashlib
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Literal

from starlette.datastructures import MutableHeaders, Secret
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class InvalidSession(Exception):
    """Raised when a session cookie cannot be parsed or verified."""


class SimpleSessionMiddleware:
    """Cookie-based session middleware using HMAC signing."""

    def __init__(
        self,
        app: ASGIApp,
        secret_key: str | Secret,
        session_cookie: str = "session",
        max_age: int | None = 14 * 24 * 60 * 60,
        path: str = "/",
        same_site: Literal["lax", "strict", "none"] = "lax",
        https_only: bool = False,
        domain: str | None = None,
    ) -> None:
        self.app = app
        self.secret = str(secret_key).encode("utf-8")
        self.session_cookie = session_cookie
        self.max_age = max_age
        self.path = path
        self.security_flags = "httponly; samesite=" + same_site
        if https_only:
            self.security_flags += "; secure"
        if domain:
            self.security_flags += f"; domain={domain}"

    def _sign(self, payload: bytes) -> str:
        digest = hmac.new(self.secret, payload, hashlib.sha256).hexdigest()
        return digest

    def _encode(self, session: dict[str, object]) -> str:
        raw = json.dumps(session, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        body = urlsafe_b64encode(raw)
        timestamp = str(int(time.time())).encode("ascii")
        base = body + b":" + timestamp
        signature = self._sign(base).encode("ascii")
        return (base + b":" + signature).decode("ascii")

    def _decode(self, data: str) -> dict[str, object]:
        try:
            body, ts_bytes, signature = data.encode("ascii").rsplit(b":", 2)
        except ValueError as exc:
            raise InvalidSession("Malformed session token") from exc
        expected = self._sign(body + b":" + ts_bytes)
        if not hmac.compare_digest(signature.decode("ascii"), expected):
            raise InvalidSession("Signature mismatch")
        if self.max_age is not None:
            ts = int(ts_bytes.decode("ascii"))
            if time.time() - ts > self.max_age:
                raise InvalidSession("Session expired")
        raw = urlsafe_b64decode(body)
        return json.loads(raw.decode("utf-8"))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        connection = HTTPConnection(scope)
        initial_session_was_empty = True

        if self.session_cookie in connection.cookies:
            token = connection.cookies[self.session_cookie]
            try:
                scope["session"] = self._decode(token)
                initial_session_was_empty = False
            except InvalidSession:
                scope["session"] = {}
        else:
            scope["session"] = {}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if scope["session"]:
                    encoded = self._encode(scope["session"])
                    header_value = (
                        f"{self.session_cookie}={encoded}; path={self.path}; "
                        f"{'Max-Age=' + str(self.max_age) + '; ' if self.max_age else ''}"
                        f"{self.security_flags}"
                    )
                    headers.append("Set-Cookie", header_value)
                elif not initial_session_was_empty:
                    header_value = (
                        f"{self.session_cookie}=null; path={self.path}; "
                        f"expires=Thu, 01 Jan 1970 00:00:00 GMT; {self.security_flags}"
                    )
                    headers.append("Set-Cookie", header_value)
            await send(message)

        await self.app(scope, receive, send_wrapper)
