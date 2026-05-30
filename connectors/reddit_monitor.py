from __future__ import annotations
import base64
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import httpx
import praw
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


def _get_reddit() -> praw.Reddit:
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID", ""),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET", ""),
        username=os.getenv("REDDIT_USERNAME", ""),
        password=os.getenv("REDDIT_PASSWORD", ""),
        user_agent=os.getenv("REDDIT_USER_AGENT", "CulinaAI FoodRescueBot/1.0"),
    )


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


def _collect_images(submission: praw.models.Submission) -> list[str]:
    images: list[str] = []

    # Direct image link (jpg/png/gif/webp)
    url = getattr(submission, "url", "") or ""
    ext = os.path.splitext(url.lower().split("?")[0])[1]
    if ext in _IMAGE_EXTS:
        b64 = _download_image_b64(url)
        if b64:
            images.append(b64)

    # Reddit gallery (multiple images)
    if getattr(submission, "is_gallery", False):
        media_metadata = getattr(submission, "media_metadata", {}) or {}
        for item in list(media_metadata.values())[:_MAX_IMAGES]:
            if item.get("status") != "valid":
                continue
            img_url = item.get("s", {}).get("u", "")
            if img_url:
                b64 = _download_image_b64(img_url.replace("&amp;", "&"))
                if b64:
                    images.append(b64)
                    if len(images) >= _MAX_IMAGES:
                        break

    return images[:_MAX_IMAGES]


def _call_analyze(
    text: str,
    images: list[str],
    submission: praw.models.Submission,
) -> None:
    payload = {
        "text": text,
        "images": images,
        "platform": "reddit",
        "idempotency_key": f"reddit:{submission.id}",
        "source_metadata": {
            "subreddit": submission.subreddit.display_name,
            "post_title": submission.title,
            "post_url": f"https://reddit.com{submission.permalink}",
            "reddit_post_id": submission.id,
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
        post_id=submission.id,
        analysis_id=resp.json().get("analysis_id"),
    )


def monitor() -> None:
    reddit = _get_reddit()
    subreddit = reddit.subreddit(SUBREDDITS)

    log.info("reddit_monitor_started", subreddits=SUBREDDITS)

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

            images = _collect_images(submission)
            _call_analyze(text, images, submission)

        except Exception as exc:
            log.error(
                "reddit_post_processing_failed",
                post_id=getattr(submission, "id", "unknown"),
                error=str(exc),
            )


if __name__ == "__main__":
    monitor()
