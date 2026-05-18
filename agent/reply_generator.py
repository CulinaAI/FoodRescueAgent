from __future__ import annotations
from api.models import (
    RescuePlan,
    ReplyDraft,
    FOOD_SAFETY_DISCLAIMER_EN,
    FOOD_SAFETY_DISCLAIMER_TR,
)
from agent.risk_engine import PrioritizedIngredient

_TEMPLATES: dict[str, str] = {
    "reddit": (
        "Great haul! A few things need attention before they turn. 🌿\n\n"
        "**🚨 Use today (high-risk):** {high_risk_summary}\n\n"
        "{recipes_section}"
        "**Storage tips:**\n{storage_tips}\n\n"
        "{disclaimer}"
    ),
    "telegram": (
        "🌿 Hızlı Kurtarma Planı!\n\n"
        "⚠️ Bugün kullan: {high_risk_summary}\n\n"
        "{recipes_section}"
        "💡 {storage_tip_1}\n\n"
        "{disclaimer}"
    ),
    "generic": (
        "Food Rescue Plan 🌿\n\n"
        "⚠️ Use today: {high_risk_summary}\n\n"
        "{recipes_section}"
        "Tips: {storage_tips}\n\n"
        "{disclaimer}"
    ),
    "manual": (
        "Food Rescue Plan 🌿\n\n"
        "⚠️ Use today: {high_risk_summary}\n\n"
        "{recipes_section}"
        "Tips: {storage_tips}\n\n"
        "{disclaimer}"
    ),
}


def _format_reddit_recipe(recipe, index: int) -> str:
    steps = "\n".join(f"{i+1}. {s}" for i, s in enumerate(recipe.steps[:5]))
    return (
        f"**Recipe {index} — {recipe.title}** "
        f"({recipe.prep_time_minutes} min, {recipe.difficulty})\n"
        f"*Why now: {recipe.rescue_reason}*\n"
        f"{steps}\n\n"
    )


def _format_telegram_recipe(recipe) -> str:
    steps_short = " → ".join(recipe.steps[:3])
    return f"📌 {recipe.title} ({recipe.prep_time_minutes} dk)\n{steps_short}\n\n"


def _format_generic_recipe(recipe, index: int) -> str:
    steps = "\n".join(f"{i+1}. {s}" for i, s in enumerate(recipe.steps[:5]))
    return f"Recipe {index}: {recipe.title} ({recipe.prep_time_minutes} min)\n{steps}\n\n"


def generate_reply(
    plan: RescuePlan,
    platform: str,
    prioritized: list[PrioritizedIngredient],
    use_tr: bool = False,
) -> ReplyDraft:
    disclaimer = FOOD_SAFETY_DISCLAIMER_TR if use_tr else FOOD_SAFETY_DISCLAIMER_EN
    high_risk_summary = ", ".join(plan.high_risk_ingredients) or "check all perishables"
    storage_tips_str = "\n".join(f"• {t}" for t in plan.storage_tips)
    storage_tip_1 = plan.storage_tips[0] if plan.storage_tips else "Refrigerate immediately."

    # Build recipes section per platform
    if platform == "reddit":
        recipes_section = "".join(
            _format_reddit_recipe(r, i + 1) for i, r in enumerate(plan.recipes)
        )
    elif platform == "telegram":
        recipes_section = "".join(_format_telegram_recipe(r) for r in plan.recipes)
    else:
        recipes_section = "".join(
            _format_generic_recipe(r, i + 1) for i, r in enumerate(plan.recipes)
        )

    template = _TEMPLATES.get(platform, _TEMPLATES["generic"])

    content = template.format(
        high_risk_summary=high_risk_summary,
        recipes_section=recipes_section,
        storage_tips=storage_tips_str,
        storage_tip_1=storage_tip_1,
        disclaimer=disclaimer,
    )

    # Disclaimer injection sanity check — never omit it
    if disclaimer not in content:
        content = content.rstrip() + "\n\n" + disclaimer

    # Confidence: average of ingredient confidences weighted by risk
    if prioritized:
        weights = {"high": 3, "medium": 2, "low": 1}
        weighted_sum = sum(p.confidence * weights[p.risk] for p in prioritized)
        weight_total = sum(weights[p.risk] for p in prioritized)
        confidence = weighted_sum / weight_total if weight_total else 0.5
    else:
        confidence = 0.5

    return ReplyDraft(platform=platform, content=content, confidence=round(confidence, 3))
