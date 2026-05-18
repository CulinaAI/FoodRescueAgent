"""
Integration tests — hit the real FastAPI app (TestClient, no network).
Gemini API calls are mocked with fixtures to keep tests deterministic.

Set GEMINI_INTEGRATION=true + GEMINI_API_KEY=<key> to run with real API.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("FOOD_RESCUE_API_KEY", "test-key-integration")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_fra1.db")

from api.main import app

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "gemini_responses"
_API_HEADERS = {"X-API-Key": "test-key-integration"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# ── A: text + vision → full rescue plan ──────────────────────────────────────

def test_analyze_with_text_returns_rescue_plan(client):
    payload = {
        "text": "I have spinach that's going bad today and no freezer.",
        "platform": "manual",
        "idempotency_key": "integ-test-a",
    }
    resp = client.post("/analyze", json=payload, headers=_API_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_food_rescue"] is True
    assert "disclaimer" in data
    assert data["disclaimer"] != ""
    assert "rescue_plan" in data


# ── B: text only (no images) ─────────────────────────────────────────────────

def test_analyze_text_only_endpoint(client):
    payload = {
        "text": "Got leftovers before they go bad, no freezer available.",
        "images": ["dGVzdA=="],  # would be ignored by /analyze/text
        "platform": "manual",
        "idempotency_key": "integ-test-b",
    }
    resp = client.post("/analyze/text", json=payload, headers=_API_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ingredients"] == []   # vision skipped


# ── C: oversized image → 413 ─────────────────────────────────────────────────

def test_oversized_image_returns_413(client):
    huge_b64 = "A" * (12 * 1024 * 1024)  # > 10MB decoded approximation
    import base64
    # Simulate > 10MB by creating a large base64 payload
    large_bytes = b"X" * (11 * 1024 * 1024)
    b64 = base64.b64encode(large_bytes).decode()
    payload = {
        "text": "leftovers going bad today, no freezer",
        "images": [b64],
        "platform": "manual",
        "idempotency_key": "integ-test-c",
    }
    resp = client.post("/analyze", json=payload, headers=_API_HEADERS)
    assert resp.status_code == 413


# ── D: wrong API key → 401 ────────────────────────────────────────────────────

def test_wrong_api_key_returns_401(client):
    payload = {"text": "spinach going bad", "platform": "manual"}
    resp = client.post("/analyze", json=payload, headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401


# ── E: idempotency — same key twice returns cached ───────────────────────────

def test_idempotency_key_returns_cached(client):
    payload = {
        "text": "I have mushrooms going bad today, no freezer.",
        "platform": "manual",
        "idempotency_key": "integ-test-e-unique",
    }
    r1 = client.post("/analyze", json=payload, headers=_API_HEADERS)
    assert r1.status_code == 200
    aid1 = r1.json()["analysis_id"]

    r2 = client.post("/analyze", json=payload, headers=_API_HEADERS)
    assert r2.status_code == 200
    aid2 = r2.json()["analysis_id"]

    assert aid1 == aid2  # same analysis_id returned for same idempotency_key


# ── Health ────────────────────────────────────────────────────────────────────

def test_health_endpoint_no_auth(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── Too many images → 400 ─────────────────────────────────────────────────────

def test_too_many_images_returns_400(client):
    import base64
    small = base64.b64encode(b"x").decode()
    payload = {
        "text": "spinach going bad today, no freezer",
        "images": [small] * 11,  # > 10
        "platform": "manual",
    }
    resp = client.post("/analyze", json=payload, headers=_API_HEADERS)
    assert resp.status_code == 400
