import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent.vision import analyze_images, _dedup_ingredients
from api.models import ScannedIngredient


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "gemini_responses"


def _make_ingredient(**kwargs) -> ScannedIngredient:
    defaults = {
        "name": "spinach",
        "visual_condition": "fresh",
        "spoilage_risk": "high",
        "storage_category": "fridge",
        "confidence": 0.9,
    }
    defaults.update(kwargs)
    return ScannedIngredient(**defaults)


def _mock_client(response_items: list[dict]) -> MagicMock:
    client = MagicMock()
    response = MagicMock()
    response.text = json.dumps(response_items)
    client.models.generate_content.return_value = response
    return client


def test_no_images_returns_empty():
    result = analyze_images([])
    assert result == []


def test_low_confidence_item_excluded():
    items = [
        {"name": "spinach", "visual_condition": "fresh", "spoilage_risk": "high",
         "storage_category": "fridge", "confidence": 0.2},
    ]
    client = _mock_client(items)
    with patch("agent.vision._decode_image_to_temp") as mock_decode, \
         patch("pathlib.Path.stat") as mock_stat, \
         patch("pathlib.Path.read_bytes") as mock_read, \
         patch("os.unlink"):
        mock_decode.return_value = ("/tmp/fake.jpg", "image/jpeg")
        mock_stat.return_value.st_size = 1024
        mock_read.return_value = b"fake"
        result = analyze_images(["dGVzdA=="], client=client)
    assert result == []  # confidence 0.2 < 0.3 threshold


def test_multi_image_dedup_keeps_higher_confidence():
    a = _make_ingredient(name="spinach", confidence=0.6)
    b = _make_ingredient(name="spinach", confidence=0.9)
    result = _dedup_ingredients([a, b])
    assert len(result) == 1
    assert result[0].confidence == 0.9


def test_multi_image_dedup_different_ingredients():
    a = _make_ingredient(name="spinach")
    b = _make_ingredient(name="carrots", visual_condition="fresh", spoilage_risk="low")
    result = _dedup_ingredients([a, b])
    assert len(result) == 2
