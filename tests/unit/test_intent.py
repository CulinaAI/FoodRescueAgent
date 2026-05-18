import pytest
from agent.intent import detect_intent


# ── Positive scenarios ────────────────────────────────────────────────────────

def test_spoilage_and_time_pressure():
    result = detect_intent("I need to use this spinach before it goes bad, tonight!", has_image=False)
    assert result.is_food_rescue is True
    assert result.score >= 2
    assert "spoilage" in result.rescue_signal_names
    assert result.time_pressure == "tonight"


def test_no_freezer_and_leftovers():
    result = detect_intent("Got lots of leftovers and no freezer space.", has_image=False)
    assert result.is_food_rescue is True
    assert result.no_freezer is True
    assert "leftovers" in result.rescue_signal_names


def test_turkish_signals():
    result = detect_intent("Dondurucu yok, ıspanağımı kullanmak istiyorum bugün.", has_image=False)
    assert result.is_food_rescue is True
    assert result.no_freezer is True
    assert result.time_pressure == "today"


def test_image_plus_spoilage():
    result = detect_intent("These are going bad", has_image=True)
    assert result.is_food_rescue is True
    assert result.score >= 2


def test_budget_and_leftovers():
    result = detect_intent("Want to use up these leftovers on a budget.", has_image=False)
    assert result.is_food_rescue is True
    assert "budget" in result.rescue_signal_names
    assert "leftovers" in result.rescue_signal_names


# ── Negative scenarios ────────────────────────────────────────────────────────

def test_general_recipe_question():
    result = detect_intent("What's a good pasta recipe?", has_image=False)
    assert result.is_food_rescue is False


def test_restaurant_recommendation():
    result = detect_intent("Looking for a good restaurant in Istanbul.", has_image=False)
    assert result.is_food_rescue is False


def test_cooking_technique_question():
    result = detect_intent("How do I properly sear a steak?", has_image=False)
    assert result.is_food_rescue is False


def test_shopping_question():
    result = detect_intent("What should I buy at the grocery store?", has_image=False)
    assert result.is_food_rescue is False


def test_empty_text_no_image():
    result = detect_intent("", has_image=False)
    assert result.is_food_rescue is False
    assert result.score == 0


# ── People count extraction ───────────────────────────────────────────────────

def test_people_count_extraction():
    result = detect_intent("Cooking for a family of 4, need to use up these leftovers today!", has_image=False)
    assert result.people_count == 4


def test_people_count_default():
    result = detect_intent("Using up these leftovers today before they go bad.", has_image=False)
    assert result.people_count == 1
