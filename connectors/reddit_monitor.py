from __future__ import annotations
import base64
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
import structlog

from agent.intent import detect_intent

log = structlog.get_logger()

SUBREDDITS = os.getenv(
    "REDDIT_SUBREDDITS",
    "noscrapleftbehind+mealprep+EatCheapAndHealthy",
)
_AGENT_URL = os.getenv("FOOD_RESCUE_AGENT_URL", "http://localhost:8080")
_API_KEY = os.getenv("FOOD_RESCUE_API_KEY", "")
_MAX_IMAGES = int(os.getenv("MAX_IMAGES_PER_REQUEST", "10"))
_MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_SIZE_MB", "10")) * 1024 * 1024
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
_POLL_INTERVAL = int(os.getenv("REDDIT_POLL_INTERVAL_SEC", "90"))

# Credentials are "real" when CLIENT_ID is not empty and not the placeholder.
_DUMMY_VALUES = {"", "dummy_client_id", "YOUR_CLIENT_ID"}
_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
_USE_PRAW = _CLIENT_ID not in _DUMMY_VALUES


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _download_image_b64(url: str) -> str | None:
    try:
        resp = httpx.get(url, timeout=10, follow_redirects=True)
        resp.raise_for_status()
        if len(resp.content) > _MAX_IMAGE_BYTES:
            log.warning("reddit_image_too_large", size=len(resp.content))
            return None
        return base64.b64encode(resp.content).decode()
    except Exception as exc:
        log.warning("reddit_image_download_failed", error=str(exc))
        return None


def _call_analyze(
    text: str,
    images: list[str],
    post_id: str,
    subreddit: str,
    post_title: str,
    post_url: str,
) -> None:
    payload = {
        "text": text,
        "images": images,
        "platform": "reddit",
        "idempotency_key": f"reddit:{post_id}",
        "source_metadata": {
            "subreddit": subreddit,
            "post_title": post_title,
            "post_url": post_url,
            "reddit_post_id": post_id,
        },
    }
    resp = httpx.post(
        f"{_AGENT_URL}/analyze",
        json=payload,
        headers={"X-API-Key": _API_KEY},
        timeout=60.0,
    )
    resp.raise_for_status()
    log.info(
        "reddit_post_analyzed",
        post_id=post_id,
        analysis_id=resp.json().get("analysis_id"),
    )


# ---------------------------------------------------------------------------
# Mode A: PRAW streaming (requires real client_id + client_secret)
# ---------------------------------------------------------------------------

def _monitor_praw() -> None:
    """Stream submissions via PRAW. Requires a Reddit script-app OAuth key."""
    import praw  # noqa: PLC0415  (import only when actually used)

    username = os.getenv("REDDIT_USERNAME", "")
    password = os.getenv("REDDIT_PASSWORD", "")
    kwargs: dict = {
        "client_id": _CLIENT_ID,
        "client_secret": os.getenv("REDDIT_CLIENT_SECRET", ""),
        "user_agent": os.getenv("REDDIT_USER_AGENT", "CulinaAI FoodRescueBot/1.0"),
    }
    if username and password:
        kwargs["username"] = username
        kwargs["password"] = password

    reddit = praw.Reddit(**kwargs)
    subreddit = reddit.subreddit(SUBREDDITS)
    log.info("reddit_monitor_started", mode="praw", subreddits=SUBREDDITS)

    for submission in subreddit.stream.submissions(skip_existing=True):
        try:
            text = f"{submission.title}\n\n{submission.selftext or ''}".strip()
            has_image = (
                getattr(submission, "post_hint", "") == "image"
                or getattr(submission, "is_gallery", False)
            )
            intent = detect_intent(text, has_image=has_image)
            if not intent.is_food_rescue:
                log.debug("reddit_post_skipped", post_id=submission.id)
                continue

            # Collect images
            images: list[str] = []
            url = getattr(submission, "url", "") or ""
            ext = os.path.splitext(url.lower().split("?")[0])[1]
            if ext in _IMAGE_EXTS:
                b64 = _download_image_b64(url)
                if b64:
                    images.append(b64)

            if getattr(submission, "is_gallery", False):
                for item in list((getattr(submission, "media_metadata", {}) or {}).values())[:_MAX_IMAGES]:
                    if item.get("status") != "valid":
                        continue
                    img_url = item.get("s", {}).get("u", "")
                    if img_url:
                        b64 = _download_image_b64(img_url.replace("&amp;", "&"))
                        if b64:
                            images.append(b64)
                            if len(images) >= _MAX_IMAGES:
                                break

            _call_analyze(
                text=text,
                images=images[:_MAX_IMAGES],
                post_id=submission.id,
                subreddit=submission.subreddit.display_name,
                post_title=submission.title,
                post_url=f"https://reddit.com{submission.permalink}",
            )

        except Exception as exc:
            log.error(
                "reddit_post_processing_failed",
                post_id=getattr(submission, "id", "unknown"),
                error=str(exc),
            )


# ---------------------------------------------------------------------------
# Mode B: Public JSON API polling (zero credentials needed)
# ---------------------------------------------------------------------------

def _fetch_new_posts(after: str | None = None) -> tuple[list[dict], str | None]:
    """Fetch up to 100 newest posts from target subreddits via public JSON."""
    url = f"https://www.reddit.com/r/{SUBREDDITS}/new.json"
    params: dict = {"limit": 100, "raw_json": 1}
    if after:
        params["after"] = after

    headers = {"User-Agent": "CulinaAI FoodRescueBot/1.0 (no-auth poll)"}
    try:
        resp = httpx.get(url, params=params, headers=headers, timeout=20, follow_redirects=True)
        resp.raise_for_status()
        data = resp.json()
        posts = [child["data"] for child in data.get("data", {}).get("children", [])]
        new_after = data.get("data", {}).get("after")
        return posts, new_after
    except Exception as exc:
        log.warning("reddit_json_fetch_failed", error=str(exc))
        return [], after


def _collect_images_from_post(post: dict) -> list[str]:
    images: list[str] = []
    url = post.get("url", "") or ""
    ext = os.path.splitext(url.lower().split("?")[0])[1]
    if ext in _IMAGE_EXTS:
        b64 = _download_image_b64(url)
        if b64:
            images.append(b64)

    # Gallery
    if post.get("is_gallery"):
        for item in list((post.get("media_metadata") or {}).values())[:_MAX_IMAGES]:
            if item.get("status") != "valid":
                continue
            img_url = (item.get("s") or {}).get("u", "")
            if img_url:
                b64 = _download_image_b64(img_url.replace("&amp;", "&"))
                if b64:
                    images.append(b64)
                    if len(images) >= _MAX_IMAGES:
                        break

    return images[:_MAX_IMAGES]


def _monitor_json_poll() -> None:
    """Poll Reddit's public /new.json endpoint. No credentials required."""
    log.info("reddit_monitor_started", mode="json_poll", subreddits=SUBREDDITS, interval_sec=_POLL_INTERVAL)

    seen: set[str] = set()
    # Bootstrap: fetch once to seed `seen` so we don't re-analyze historical posts.
    posts, _ = _fetch_new_posts()
    seen.update(p["id"] for p in posts)
    log.info("reddit_poll_bootstrap", seen_count=len(seen))

    while True:
        time.sleep(_POLL_INTERVAL)
        posts, _ = _fetch_new_posts()

        new_posts = [p for p in posts if p["id"] not in seen]
        log.info("reddit_poll_cycle", new_posts=len(new_posts), total_fetched=len(posts))

        for post in new_posts:
            seen.add(post["id"])
            try:
                text = f"{post.get('title', '')}\n\n{post.get('selftext', '') or ''}".strip()
                has_image = (
                    post.get("post_hint") == "image"
                    or bool(post.get("is_gallery"))
                    or any(post.get("url", "").lower().endswith(ext) for ext in _IMAGE_EXTS)
                )
                intent = detect_intent(text, has_image=has_image)
                if not intent.is_food_rescue:
                    log.debug("reddit_post_skipped", post_id=post["id"])
                    continue

                images = _collect_images_from_post(post)
                _call_analyze(
                    text=text,
                    images=images,
                    post_id=post["id"],
                    subreddit=post.get("subreddit", ""),
                    post_title=post.get("title", ""),
                    post_url=f"https://reddit.com{post.get('permalink', '')}",
                )

            except Exception as exc:
                log.error(
                    "reddit_post_processing_failed",
                    post_id=post.get("id", "unknown"),
                    error=str(exc),
                )

        # Bound memory: keep only most recent 5000 IDs
        if len(seen) > 5000:
            seen = set(list(seen)[-5000:])


# ---------------------------------------------------------------------------
# Entry point — auto-selects mode
# ---------------------------------------------------------------------------

def monitor() -> None:
    if _USE_PRAW:
        log.info("reddit_monitor_mode", mode="praw", reason="REDDIT_CLIENT_ID configured")
        _monitor_praw()
    else:
        log.info("reddit_monitor_mode", mode="json_poll", reason="no valid REDDIT_CLIENT_ID")
        _monitor_json_poll()


if __name__ == "__main__":
    monitor()
