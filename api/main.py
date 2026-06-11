import base64
import json
import os
import time
import uuid

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from agent.intent import detect_intent
from agent.reply_generator import generate_reply
from agent.rescue_planner import generate_rescue_plan
from agent.risk_engine import score_ingredients
from agent.vision import analyze_images
from api.models import (
    AnalyzeRequest,
    AnalyzeResponse,
    FOOD_SAFETY_DISCLAIMER_EN,
    FOOD_SAFETY_DISCLAIMER_TR,
    HealthResponse,
    MetricsResponse,
)
from api.security import verify_api_key
from db.models import (
    HitlReview,
    RescueAnalysis,
    RescueDraft,
    RescuePost,
    create_tables,
    get_session,
)

log = structlog.get_logger()

_RATE_LIMIT = f"{os.getenv('RATE_LIMIT_PER_MIN', '60')}/minute"
_MAX_IMAGES = int(os.getenv("MAX_IMAGES_PER_REQUEST", "10"))
_MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_SIZE_MB", "10")) * 1024 * 1024

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="CulinaAI Food Rescue Agent", version="1.0.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.on_event("startup")
def on_startup() -> None:
    create_tables()


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok", version="1.0.0")


# ── Metrics ───────────────────────────────────────────────────────────────────

@app.get("/metrics", response_model=MetricsResponse, dependencies=[Depends(verify_api_key)])
async def metrics() -> MetricsResponse:
    with get_session() as db:
        processed = db.query(RescuePost).count()
        approved = db.query(HitlReview).filter(HitlReview.action == "approved").count()
        latencies = [
            r.latency_ms for r in db.query(RescueAnalysis).all() if r.latency_ms
        ]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0.0
    return MetricsResponse(processed=processed, approved=approved, avg_latency_ms=avg_latency)


# ── Core analysis ─────────────────────────────────────────────────────────────

def _validate_images(images: list[str]) -> None:
    if len(images) > _MAX_IMAGES:
        raise HTTPException(status_code=400, detail=f"Too many images (max {_MAX_IMAGES})")
    for img in images:
        if img.startswith("http://") or img.startswith("https://"):
            continue
        try:
            decoded = base64.b64decode(img)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 image")
        if len(decoded) > _MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="Image too large")


@app.post("/analyze", response_model=AnalyzeResponse, dependencies=[Depends(verify_api_key)])
@limiter.limit(_RATE_LIMIT)
async def analyze(request: Request, req: AnalyzeRequest) -> AnalyzeResponse:
    _validate_images(req.images)
    return await _run_analysis(req)


@app.post("/analyze/text", response_model=AnalyzeResponse, dependencies=[Depends(verify_api_key)])
@limiter.limit(_RATE_LIMIT)
async def analyze_text(request: Request, req: AnalyzeRequest) -> AnalyzeResponse:
    req.images = []  # force text-only path
    return await _run_analysis(req)


async def _run_analysis(body: AnalyzeRequest) -> AnalyzeResponse:
    t0 = time.monotonic()
    request_id = str(uuid.uuid4())

    # Idempotency check
    idempotency_key = body.idempotency_key or request_id
    with get_session() as db:
        existing_post = db.query(RescuePost).filter_by(idempotency_key=idempotency_key).first()
        if existing_post:
            analysis = (
                db.query(RescueAnalysis)
                .filter_by(post_id=existing_post.id)
                .order_by(RescueAnalysis.created_at.desc())
                .first()
            )
            draft = (
                db.query(RescueDraft)
                .filter_by(analysis_id=analysis.id)
                .first()
                if analysis
                else None
            )
            if analysis and draft:
                latency_ms = int((time.monotonic() - t0) * 1000)
                return _build_response(
                    analysis_id=analysis.id,
                    body=body,
                    analysis=analysis,
                    draft=draft,
                    latency_ms=latency_ms,
                )

    # 1. Intent detection (pure Python — no API call)
    intent = detect_intent(body.text, has_image=bool(body.images))

    log.info(
        "analysis_started",
        request_id=request_id,
        platform=body.platform,
        is_food_rescue=intent.is_food_rescue,
        image_count=len(body.images),
    )

    # 2. Vision (only if images present)
    ingredients = analyze_images(body.images) if body.images else []

    # 3. Risk scoring
    context_no_freezer = body.context.no_freezer or intent.no_freezer
    context = body.context
    context.no_freezer = context_no_freezer

    prioritized = score_ingredients(ingredients, no_freezer=context_no_freezer)

    # 4. Rescue plan (Gemini Pro)
    rescue_plan = generate_rescue_plan(prioritized, context)

    # 5. Reply draft
    use_tr = body.platform == "telegram"
    reply_draft = generate_reply(rescue_plan, body.platform, prioritized, use_tr=use_tr)

    latency_ms = int((time.monotonic() - t0) * 1000)

    # Persist
    analysis_id = str(uuid.uuid4())
    meta = body.source_metadata or {}
    with get_session() as db:
        post = RescuePost(
            id=str(uuid.uuid4()),
            idempotency_key=idempotency_key,
            source_platform=body.platform,
            source_id=meta.get("reddit_post_id"),
            raw_text=body.text,
            is_food_rescue=intent.is_food_rescue,
            urgency_hint=(
                "high" if any(p.risk == "high" for p in prioritized) else
                "medium" if any(p.risk == "medium" for p in prioritized) else "low"
            ),
            rescue_signals=json.dumps(intent.rescue_signal_names),
            subreddit=meta.get("subreddit"),
            post_title=meta.get("post_title"),
            post_url=meta.get("post_url"),
        )
        db.add(post)
        db.flush()

        analysis_row = RescueAnalysis(
            id=analysis_id,
            post_id=post.id,
            ingredients=json.dumps([i.model_dump() for i in ingredients]),
            risk_scores=json.dumps([
                {"name": p.name, "risk": p.risk, "reason": p.reason}
                for p in prioritized
            ]),
            rescue_plan=rescue_plan.model_dump_json(),
            model_used=os.getenv("GEMINI_MODEL", "gemini-flash-latest"),
            latency_ms=latency_ms,
        )
        db.add(analysis_row)
        db.flush()

        draft_row = RescueDraft(
            id=str(uuid.uuid4()),
            analysis_id=analysis_id,
            platform=body.platform,
            content=reply_draft.content,
            confidence=reply_draft.confidence,
            hitl_status="pending",
        )
        db.add(draft_row)
        db.commit()

    log.info(
        "analysis_complete",
        request_id=request_id,
        latency_ms=latency_ms,
        is_food_rescue=intent.is_food_rescue,
    )

    disclaimer = FOOD_SAFETY_DISCLAIMER_TR if use_tr else FOOD_SAFETY_DISCLAIMER_EN

    return AnalyzeResponse(
        analysis_id=analysis_id,
        is_food_rescue=intent.is_food_rescue,
        rescue_signals=intent.rescue_signal_names,
        ingredients=ingredients,
        rescue_plan=rescue_plan,
        reply_draft=reply_draft,
        disclaimer=disclaimer,
        latency_ms=latency_ms,
    )


def _build_response(
    analysis_id: str,
    body: AnalyzeRequest,
    analysis: RescueAnalysis,
    draft: RescueDraft,
    latency_ms: int,
) -> AnalyzeResponse:
    from api.models import ScannedIngredient, RescuePlan, ReplyDraft
    ingredients = [ScannedIngredient(**i) for i in json.loads(analysis.ingredients or "[]")]
    plan = RescuePlan.model_validate_json(analysis.rescue_plan or "{}")
    reply = ReplyDraft(platform=draft.platform, content=draft.content, confidence=draft.confidence or 0.5)
    use_tr = body.platform == "telegram"
    disclaimer = FOOD_SAFETY_DISCLAIMER_TR if use_tr else FOOD_SAFETY_DISCLAIMER_EN
    return AnalyzeResponse(
        analysis_id=analysis_id,
        is_food_rescue=True,
        rescue_signals=[],
        ingredients=ingredients,
        rescue_plan=plan,
        reply_draft=reply,
        disclaimer=disclaimer,
        latency_ms=latency_ms,
    )
