import pytest
from api.models import ScannedIngredient
from agent.risk_engine import score_ingredients, PrioritizedIngredient


def _make(name: str, condition: str = "fresh", risk: str = "low", confidence: float = 0.9) -> ScannedIngredient:
    return ScannedIngredient(
        name=name,
        visual_condition=condition,  # type: ignore[arg-type]
        spoilage_risk=risk,  # type: ignore[arg-type]
        storage_category="fridge",
        confidence=confidence,
    )


def test_empty_list():
    assert score_ingredients([]) == []


def test_leafy_greens_high_risk():
    result = score_ingredients([_make("spinach")])
    assert result[0].risk == "high"


def test_wilting_escalation():
    result = score_ingredients([_make("broccoli", condition="wilting")])
    # broccoli is MEDIUM, wilting escalates to HIGH
    assert result[0].risk == "high"
    assert "wilting" in result[0].reason


def test_cut_open_escalation():
    result = score_ingredients([_make("watermelon", condition="cut_open")])
    # watermelon can be HIGH already, cut_open keeps or escalates
    assert result[0].risk == "high"
    assert "cut open" in result[0].reason


def test_no_freezer_escalation():
    result = score_ingredients([_make("carrots")], no_freezer=True)
    # carrots are LOW, no_freezer escalates to MEDIUM
    assert result[0].risk == "medium"
    assert "no freezer" in result[0].reason


def test_high_risk_stays_high_with_no_freezer():
    result = score_ingredients([_make("spinach")], no_freezer=True)
    # already HIGH, stays HIGH
    assert result[0].risk == "high"


def test_sort_order_high_before_medium_before_low():
    ingredients = [
        _make("carrots"),       # LOW
        _make("spinach"),       # HIGH
        _make("broccoli"),      # MEDIUM
    ]
    result = score_ingredients(ingredients)
    risks = [r.risk for r in result]
    assert risks[0] == "high"
    assert risks[1] == "medium"
    assert risks[2] == "low"


def test_unknown_ingredient_defaults_to_low():
    result = score_ingredients([_make("mystery_ingredient_xyz")])
    assert result[0].risk == "low"


def test_confidence_tiebreak():
    # Two HIGH risk items — higher confidence comes first
    ingredients = [
        _make("mushrooms", confidence=0.6),
        _make("spinach", confidence=0.95),
    ]
    result = score_ingredients(ingredients)
    assert result[0].confidence == 0.95
