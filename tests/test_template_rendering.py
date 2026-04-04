from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

import app.dashboard as dashboard


def test_homepage_renders() -> None:
    client = TestClient(dashboard.app)
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "Lowebot" in response.text


def test_healthz_ok_when_cursor_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("CHEAPSKATER_HEALTH_STRICT", raising=False)
    monkeypatch.setattr(dashboard, "ZIP_CURSOR_FILE", tmp_path / "zip_cursor.json")

    client = TestClient(dashboard.app)
    response = client.get("/healthz")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["cursor_status"] == "missing"
