import pytest
from api.models import RescuePlan, RecipeEntry, FOOD_SAFETY_DISCLAIMER_EN, FOOD_SAFETY_DISCLAIMER_TR
from agent.reply_generator import generate_reply
from agent.risk_engine import PrioritizedIngredient


def _make_plan() -> RescuePlan:
    return RescuePlan(
        urgency_summary="Use spinach today — wilting visible",
        high_risk_ingredients=["spinach"],
        recipes=[
            RecipeEntry(
                title="Quick Spinach Sauté",
                rescue_reason="Spinach appears to be wilting — use today",
                ingredients_used=["spinach", "garlic"],
                prep_time_minutes=10,
                difficulty="easy",
                steps=["Heat oil", "Add garlic", "Add spinach", "Season"],
                no_freezer_friendly=True,
            ),
            RecipeEntry(
                title="Spinach Soup",
                rescue_reason="Second option for leftover spinach",
                ingredients_used=["spinach", "onion", "broth"],
                prep_time_minutes=20,
                difficulty="easy",
                steps=["Sauté onion", "Add spinach", "Add broth", "Blend"],
                no_freezer_friendly=True,
            ),
        ],
        storage_tips=["Store remaining spinach wrapped in paper towel"],
    )


def _make_prioritized() -> list[PrioritizedIngredient]:
    return [
        PrioritizedIngredient(
            name="spinach", risk="high", reason="Base: high",
            original_risk="high", confidence=0.9,
        )
    ]


def test_disclaimer_always_present_reddit():
    plan = _make_plan()
    draft = generate_reply(plan, "reddit", _make_prioritized(), use_tr=False)
    assert FOOD_SAFETY_DISCLAIMER_EN in draft.content


def test_disclaimer_always_present_telegram():
    plan = _make_plan()
    draft = generate_reply(plan, "telegram", _make_prioritized(), use_tr=True)
    assert FOOD_SAFETY_DISCLAIMER_TR in draft.content


def test_reddit_template_longer_than_telegram():
    plan = _make_plan()
    reddit = generate_reply(plan, "reddit", _make_prioritized())
    telegram = generate_reply(plan, "telegram", _make_prioritized())
    assert len(reddit.content) > len(telegram.content)


def test_confidence_between_0_and_1():
    plan = _make_plan()
    draft = generate_reply(plan, "generic", _make_prioritized())
    assert 0.0 <= draft.confidence <= 1.0


def test_high_risk_summary_in_output():
    plan = _make_plan()
    draft = generate_reply(plan, "reddit", _make_prioritized())
    assert "spinach" in draft.content.lower()


def test_empty_prioritized_uses_default_confidence():
    plan = _make_plan()
    draft = generate_reply(plan, "generic", [])
    assert draft.confidence == 0.5
