from typing import Literal
from pydantic import BaseModel, Field


# ── Request ──────────────────────────────────────────────────────────────────

class AnalyzeContext(BaseModel):
    no_freezer: bool = False
    people_count: int = Field(default=1, ge=1, le=20)
    time_pressure: Literal["today", "tonight", "tomorrow", "this_week"] | None = None
    dietary: list[str] = Field(default_factory=list)


class AnalyzeRequest(BaseModel):
    text: str
    images: list[str] = Field(default_factory=list)
    platform: Literal["telegram", "reddit", "manual", "generic"] = "generic"
    context: AnalyzeContext = Field(default_factory=AnalyzeContext)
    idempotency_key: str | None = None
    source_metadata: dict[str, str] | None = None


# ── Domain objects ────────────────────────────────────────────────────────────

class ScannedIngredient(BaseModel):
    name: str
    quantity_estimate: str | None = None
    visual_condition: Literal["fresh", "wilting", "cut_open", "uncertain"]
    spoilage_risk: Literal["high", "medium", "low"]
    storage_category: Literal["fridge", "pantry", "counter", "freezer"]
    confidence: float = Field(ge=0.0, le=1.0)


class RecipeEntry(BaseModel):
    title: str
    rescue_reason: str
    ingredients_used: list[str]
    prep_time_minutes: int
    difficulty: Literal["easy", "medium", "hard"]
    steps: list[str]
    no_freezer_friendly: bool


class RescuePlan(BaseModel):
    urgency_summary: str
    high_risk_ingredients: list[str]
    recipes: list[RecipeEntry]
    storage_tips: list[str]


class ReplyDraft(BaseModel):
    platform: str
    content: str
    confidence: float = Field(ge=0.0, le=1.0)


# ── Response ──────────────────────────────────────────────────────────────────

FOOD_SAFETY_DISCLAIMER_TR = (
    "⚠️ Bu öneri genel pişirme rehberliğidir. Malzemelerin tazeliğini koku ve görünüm "
    "ile doğrulayın. Saklama koşulları ve sıcaklık geçmişi bilinmediğinden, yiyecek "
    "güvenliği konusundaki son kararı siz verin. Şüphe varsa tüketmeyin. "
    "CulinaAI gıda güvenliği kararlarından sorumlu tutulamaz."
)

FOOD_SAFETY_DISCLAIMER_EN = (
    "⚠️ These are general cooking suggestions only. Verify freshness by sight and smell. "
    "Storage conditions and temperature history are unknown to us — you make the final "
    "food safety call. When in doubt, throw it out. CulinaAI is not liable for food "
    "safety decisions."
)


class AnalyzeResponse(BaseModel):
    analysis_id: str
    is_food_rescue: bool
    rescue_signals: list[str]
    ingredients: list[ScannedIngredient]
    rescue_plan: RescuePlan
    reply_draft: ReplyDraft
    disclaimer: str
    latency_ms: int


class HealthResponse(BaseModel):
    status: str
    version: str


class MetricsResponse(BaseModel):
    processed: int
    approved: int
    avg_latency_ms: float
