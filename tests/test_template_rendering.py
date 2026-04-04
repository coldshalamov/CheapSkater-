from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from app.dashboard import app


def test_homepage_renders() -> None:
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "Lowebot" in response.text

