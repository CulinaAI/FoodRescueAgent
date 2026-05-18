from __future__ import annotations
import json
import os

from google import genai
import structlog

from agent.risk_engine import PrioritizedIngredient
from api.models import AnalyzeContext, RescuePlan, RecipeEntry

log = structlog.get_logger()

_SYSTEM_INSTRUCTION = (
    "You are a food rescue chef. Your goal is waste prevention. "
    "NEVER claim food is 'safe to eat'. Use language like 'if it still smells fresh', "
    "'appears to be', 'if there's no off smell'. "
    "Never override the user's own food safety judgment."
)

_PLAN_PROMPT_TEMPLATE = """High-risk ingredients (use TODAY): {high_risk_list}
Medium-risk (use within 2-3 days): {medium_risk_list}
Constraints: {constraints_json}

Generate exactly 2 rescue recipes, ordered by urgency (most urgent first).
Each recipe MUST:
1. Use the highest-risk ingredients first
2. Be feasible without a freezer if no_freezer=true
3. Include rescue_reason explaining WHY this ingredient needs attention NOW
4. Include realistic prep_time_minutes and difficulty

Return ONLY a valid JSON object matching this schema exactly:
{{
  "urgency_summary": "one sentence describing what needs attention most urgently",
  "high_risk_ingredients": ["list of ingredient names that are high risk"],
  "recipes": [
    {{
      "title": "Recipe name",
      "rescue_reason": "Why this uses the urgent ingredients",
      "ingredients_used": ["ingredient1", "ingredient2"],
      "prep_time_minutes": 20,
      "difficulty": "easy",
      "steps": ["Step 1", "Step 2", "Step 3"],
      "no_freezer_friendly": true
    }}
  ],
  "storage_tips": ["Tip 1", "Tip 2"]
}}

Return only the JSON, no markdown fences, no extra text.
"""


def _get_client() -> genai.Client:
    return genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))


def _build_prompt(
    prioritized: list[PrioritizedIngredient],
    context: AnalyzeContext,
) -> str:
    high = [p.name for p in prioritized if p.risk == "high"]
    medium = [p.name for p in prioritized if p.risk == "medium"]
    constraints = {
        "no_freezer": context.no_freezer,
        "people_count": context.people_count,
        "time_pressure": context.time_pressure,
        "dietary": context.dietary,
    }
    return _PLAN_PROMPT_TEMPLATE.format(
        high_risk_list=", ".join(high) if high else "none",
        medium_risk_list=", ".join(medium) if medium else "none",
        constraints_json=json.dumps(constraints),
    )


def generate_rescue_plan(
    prioritized: list[PrioritizedIngredient],
    context: AnalyzeContext,
    client: genai.Client | None = None,
) -> RescuePlan:
    if client is None:
        client = _get_client()

    prompt = _build_prompt(prioritized, context)

    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            from google.genai import types as genai_types
            response = client.models.generate_content(
                model="gemini-flash-latest",
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    system_instruction=_SYSTEM_INSTRUCTION,
                ),
            )
            raw = response.text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            data = json.loads(raw)
            # Validate each recipe entry
            recipes = [RecipeEntry(**r) for r in data.get("recipes", [])]
            return RescuePlan(
                urgency_summary=data["urgency_summary"],
                high_risk_ingredients=data.get("high_risk_ingredients", []),
                recipes=recipes,
                storage_tips=data.get("storage_tips", []),
            )
        except Exception as exc:
            last_exc = exc
            log.warning("rescue_plan_parse_failed", attempt=attempt, error=str(exc))

    # Fallback plan when Gemini fails
    log.error("rescue_plan_generation_failed", error=str(last_exc))
    high_names = [p.name for p in prioritized if p.risk == "high"]
    return RescuePlan(
        urgency_summary=f"Use immediately: {', '.join(high_names)}" if high_names else "Check your ingredients soon.",
        high_risk_ingredients=high_names,
        recipes=[],
        storage_tips=["Refrigerate perishables immediately.", "If in doubt, throw it out."],
    )
