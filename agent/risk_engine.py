from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from api.models import ScannedIngredient

_RULES_PATH = Path(__file__).parent.parent / "data" / "spoilage_rules.json"
_rules: dict | None = None


def _load_rules() -> dict:
    global _rules
    if _rules is None:
        _rules = json.loads(_RULES_PATH.read_text(encoding="utf-8"))
    return _rules


RiskLevel = Literal["high", "medium", "low"]
_LEVEL_ORDER = {"high": 0, "medium": 1, "low": 2}
_LEVEL_UP: dict[RiskLevel, RiskLevel] = {"low": "medium", "medium": "high", "high": "high"}


@dataclass
class PrioritizedIngredient:
    name: str
    risk: RiskLevel
    reason: str
    original_risk: RiskLevel
    confidence: float
    quantity_estimate: str | None = None
    visual_condition: str = "uncertain"


def _fuzzy_match(name: str, candidates: list[str]) -> bool:
    name_lower = name.lower()
    for c in candidates:
        if c in name_lower or name_lower in c:
            return True
    return False


def _lookup_base_risk(name: str, rules: dict) -> RiskLevel:
    for level in ("HIGH", "MEDIUM", "LOW"):
        if _fuzzy_match(name, rules[level]["ingredients"]):
            return level.lower()  # type: ignore[return-value]
    return "low"  # default: treat unknown as low risk


def score_ingredients(
    ingredients: list[ScannedIngredient],
    no_freezer: bool = False,
) -> list[PrioritizedIngredient]:
    """Assign and sort risk levels. Higher-risk items come first."""
    if not ingredients:
        return []

    rules = _load_rules()
    result: list[PrioritizedIngredient] = []

    for ing in ingredients:
        base_risk = _lookup_base_risk(ing.name, rules)
        risk = base_risk
        reasons: list[str] = []

        # Escalate from visual condition
        if ing.visual_condition == "wilting":
            risk = _LEVEL_UP[risk]
            reasons.append("wilting visible")
        elif ing.visual_condition == "cut_open":
            risk = _LEVEL_UP[risk]
            reasons.append("cut open — oxidation accelerated")

        # Escalate if no freezer option
        if no_freezer and risk != "high":
            # Cannot freeze to extend shelf life
            risk = _LEVEL_UP[risk]
            reasons.append("no freezer available")

        reason = f"Base: {base_risk}"
        if reasons:
            reason += f" → escalated ({', '.join(reasons)})"

        result.append(PrioritizedIngredient(
            name=ing.name,
            risk=risk,
            reason=reason,
            original_risk=base_risk,
            confidence=ing.confidence,
            quantity_estimate=ing.quantity_estimate,
            visual_condition=ing.visual_condition,
        ))

    # Sort: HIGH first, then MEDIUM, then LOW; within same level by confidence desc
    result.sort(key=lambda x: (_LEVEL_ORDER[x.risk], -x.confidence))
    return result
