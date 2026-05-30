import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from google import genai
from agent.rescue_planner import generate_rescue_plan
from agent.risk_engine import PrioritizedIngredient
from api.models import AnalyzeContext

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "gemini_responses"


def _make_prioritized() -> list[PrioritizedIngredient]:
    return [
        PrioritizedIngredient(
            name="spinach", risk="high", reason="Wilting",
            original_risk="high", confidence=0.9
        ),
        PrioritizedIngredient(
            name="mushrooms", risk="medium", reason="Slight odor",
            original_risk="medium", confidence=0.8
        )
    ]


def test_generate_rescue_plan_success():
    fixture_path = FIXTURE_DIR / "rescue_plan_sample_1.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        sample_json = f.read()

    client = MagicMock()
    response = MagicMock()
    response.text = sample_json
    client.models.generate_content.return_value = response

    context = AnalyzeContext(no_freezer=True, people_count=2)
    plan = generate_rescue_plan(_make_prioritized(), context, client=client)

    assert plan.urgency_summary == "Use spinach and mushrooms today — spinach is wilting and both will deteriorate quickly without freezing."
    assert plan.high_risk_ingredients == ["spinach", "mushrooms"]
    assert len(plan.recipes) == 2
    assert plan.recipes[0].title == "Wilted Spinach & Mushroom Stir-Fry"
    assert plan.recipes[0].no_freezer_friendly is True
    assert plan.storage_tips == [
        "Carrots can be stored in a sealed bag in the fridge for up to 2 weeks",
        "If mushrooms develop sliminess, discard immediately"
    ]


def test_generate_rescue_plan_with_markdown_fences():
    fixture_path = FIXTURE_DIR / "rescue_plan_sample_1.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        sample_json = f.read()

    markdown_json = f"```json\n{sample_json}\n```"

    client = MagicMock()
    response = MagicMock()
    response.text = markdown_json
    client.models.generate_content.return_value = response

    context = AnalyzeContext(no_freezer=False)
    plan = generate_rescue_plan(_make_prioritized(), context, client=client)

    assert plan.urgency_summary == "Use spinach and mushrooms today — spinach is wilting and both will deteriorate quickly without freezing."
    assert len(plan.recipes) == 2


def test_generate_rescue_plan_retry_on_invalid_json():
    client = MagicMock()
    
    bad_response = MagicMock()
    bad_response.text = "invalid json data"
    
    good_response = MagicMock()
    fixture_path = FIXTURE_DIR / "rescue_plan_sample_1.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        good_response.text = f.read()

    # First returns bad, second returns good
    client.models.generate_content.side_effect = [bad_response, good_response]

    context = AnalyzeContext(no_freezer=False)
    plan = generate_rescue_plan(_make_prioritized(), context, client=client)

    assert plan.urgency_summary == "Use spinach and mushrooms today — spinach is wilting and both will deteriorate quickly without freezing."
    assert client.models.generate_content.call_count == 2


def test_generate_rescue_plan_fallback_on_failure():
    client = MagicMock()
    bad_response = MagicMock()
    bad_response.text = "invalid json data"
    client.models.generate_content.return_value = bad_response

    context = AnalyzeContext(no_freezer=False)
    plan = generate_rescue_plan(_make_prioritized(), context, client=client)

    assert plan.urgency_summary == "Use immediately: spinach"
    assert plan.high_risk_ingredients == ["spinach"]
    assert plan.recipes == []
    assert len(plan.storage_tips) == 2


@patch("agent.rescue_planner._get_client")
def test_generate_rescue_plan_gets_default_client(mock_get_client):
    client = MagicMock()
    mock_get_client.return_value = client
    
    fixture_path = FIXTURE_DIR / "rescue_plan_sample_1.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        sample_json = f.read()

    response = MagicMock()
    response.text = sample_json
    client.models.generate_content.return_value = response

    context = AnalyzeContext(no_freezer=False)
    plan = generate_rescue_plan(_make_prioritized(), context, client=None)

    mock_get_client.assert_called_once()
    assert plan.urgency_summary == "Use spinach and mushrooms today — spinach is wilting and both will deteriorate quickly without freezing."
