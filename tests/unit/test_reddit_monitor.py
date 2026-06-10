"""Unit tests for the Reddit monitor (PRIMARY channel).

praw is stubbed in sys.modules so these run with or without praw installed
(CI installs it via requirements; local dev may not). The monitor's helpers use
duck-typed submission attributes, not praw at runtime (annotations are lazy via
`from __future__ import annotations`), so stubbing the import is sufficient.
"""
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

# ── Stub praw before importing the module under test ──────────────────────────
if "praw" not in sys.modules:
    _praw = types.ModuleType("praw")
    _praw.models = types.SimpleNamespace(Submission=object)
    _praw.Reddit = MagicMock
    sys.modules["praw"] = _praw

from connectors import reddit_monitor  # noqa: E402


def _submission(**kwargs):
    """Minimal duck-typed Reddit submission."""
    defaults = dict(
        id="abc123",
        url="https://reddit.com/r/x/comments/abc123",
        is_gallery=False,
        media_metadata={},
        title="Help, fridge full",
        permalink="/r/noscrapleftbehind/comments/abc123/",
        subreddit=SimpleNamespace(display_name="noscrapleftbehind"),
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_collect_images_direct_link(monkeypatch):
    monkeypatch.setattr(reddit_monitor, "_download_image_b64", lambda u: "B64")
    sub = _submission(url="https://i.redd.it/photo.jpg")
    assert reddit_monitor._collect_images(sub) == ["B64"]


def test_collect_images_non_image_url_returns_empty(monkeypatch):
    monkeypatch.setattr(reddit_monitor, "_download_image_b64", lambda u: "B64")
    sub = _submission(url="https://reddit.com/r/x/comments/abc123")
    assert reddit_monitor._collect_images(sub) == []


def test_collect_images_gallery(monkeypatch):
    monkeypatch.setattr(reddit_monitor, "_download_image_b64", lambda u: "B64")
    sub = _submission(
        url="https://reddit.com/gallery/abc123",
        is_gallery=True,
        media_metadata={
            "a": {"status": "valid", "s": {"u": "https://i.redd.it/1.jpg"}},
            "b": {"status": "valid", "s": {"u": "https://i.redd.it/2.jpg"}},
            "c": {"status": "failed", "s": {"u": "https://i.redd.it/3.jpg"}},
        },
    )
    images = reddit_monitor._collect_images(sub)
    assert images == ["B64", "B64"]  # 2 valid, 1 skipped


def test_call_analyze_payload_shape(monkeypatch):
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={"analysis_id": "an-1"})
        return resp

    monkeypatch.setattr(reddit_monitor.httpx, "post", fake_post)
    monkeypatch.setattr(reddit_monitor, "_API_KEY", "secret-key")

    sub = _submission(id="zzz")
    reddit_monitor._call_analyze("some text", ["IMG"], sub)

    assert captured["url"].endswith("/analyze")
    body = captured["json"]
    assert body["platform"] == "reddit"
    assert body["idempotency_key"] == "reddit:zzz"
    assert body["images"] == ["IMG"]
    assert body["source_metadata"]["subreddit"] == "noscrapleftbehind"
    assert body["source_metadata"]["reddit_post_id"] == "zzz"
    assert captured["headers"]["X-API-Key"] == "secret-key"
