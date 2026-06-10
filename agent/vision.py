from __future__ import annotations
import base64
import json
import os
import tempfile
from pathlib import Path

from google import genai
from google.genai import types as genai_types
import structlog

from agent.genai_client import get_genai_client, model_name
from api.models import ScannedIngredient

log = structlog.get_logger()

_VISION_PROMPT = """You are a food ingredient analyst. Analyze the image objectively.
NEVER claim any ingredient is "safe to eat". Use hedged language like "appears to be" or "if it still smells fresh".

Task: List ALL food items visible in the image. For each item return a JSON object with exactly these fields:
{
  "name": "ingredient name in English",
  "quantity_estimate": "half a watermelon" or null if unclear,
  "visual_condition": "fresh" | "wilting" | "cut_open" | "uncertain",
  "spoilage_risk": "high" | "medium" | "low",
  "storage_category": "fridge" | "pantry" | "counter" | "freezer",
  "confidence": 0.0 to 1.0
}

Rules:
- If you cannot identify an item clearly, set confidence < 0.5 and visual_condition "uncertain"
- Prioritize items that look perishable
- Return a JSON array only, no extra text

Example output:
[{"name":"spinach","quantity_estimate":"large bunch","visual_condition":"wilting","spoilage_risk":"high","storage_category":"fridge","confidence":0.92}]
"""


def _get_client() -> genai.Client:
    return get_genai_client()


def _decode_image_to_temp(b64_or_url: str) -> tuple[str, str]:
    """Returns (temp_path, mime_type). Caller must delete temp_path after use."""
    if b64_or_url.startswith("http://") or b64_or_url.startswith("https://"):
        # URL — download to temp
        import httpx
        resp = httpx.get(b64_or_url, timeout=10)
        resp.raise_for_status()
        content = resp.content
        content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    else:
        content = base64.b64decode(b64_or_url)
        content_type = "image/jpeg"

    suffix = ".jpg" if "jpeg" in content_type or "jpg" in content_type else ".png"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(content)
    tmp.close()
    return tmp.name, content_type


def _dedup_ingredients(items: list[ScannedIngredient]) -> list[ScannedIngredient]:
    seen: dict[str, ScannedIngredient] = {}
    for item in items:
        key = item.name.lower().strip()
        if key not in seen or item.confidence > seen[key].confidence:
            seen[key] = item
    return list(seen.values())


def analyze_images(
    images: list[str],
    client: genai.Client | None = None,
) -> list[ScannedIngredient]:
    """Analyze up to 10 food images and return a deduplicated ingredient list."""
    if not images:
        return []

    max_images = int(os.getenv("MAX_IMAGES_PER_REQUEST", "10"))
    max_size_bytes = int(os.getenv("MAX_IMAGE_SIZE_MB", "10")) * 1024 * 1024

    if client is None:
        client = _get_client()

    all_ingredients: list[ScannedIngredient] = []
    temp_paths: list[str] = []

    try:
        for b64_or_url in images[:max_images]:
            tmp_path, mime = _decode_image_to_temp(b64_or_url)
            temp_paths.append(tmp_path)

            size = Path(tmp_path).stat().st_size
            if size > max_size_bytes:
                log.warning("image_too_large", size=size, limit=max_size_bytes)
                continue

            image_bytes = Path(tmp_path).read_bytes()
            image_part = genai_types.Part.from_bytes(data=image_bytes, mime_type=mime)

            try:
                response = client.models.generate_content(
                    model=model_name(),
                    contents=[_VISION_PROMPT, image_part],
                )
                raw = response.text.strip()
                # strip markdown code fences if present
                if raw.startswith("```"):
                    raw = raw.split("```")[1]
                    if raw.startswith("json"):
                        raw = raw[4:]
                    raw = raw.strip()

                parsed = json.loads(raw)
                for item in parsed:
                    try:
                        ingredient = ScannedIngredient(**item)
                        if ingredient.confidence >= 0.3:
                            all_ingredients.append(ingredient)
                    except Exception:
                        pass
            except Exception as exc:
                log.warning("vision_single_image_failed", error=str(exc))
    finally:
        for p in temp_paths:
            try:
                os.unlink(p)
            except OSError:
                pass

    return _dedup_ingredients(all_ingredients)
