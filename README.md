# 🌿 CulinaAI Food Rescue Agent (FRACC)

> **Google for Startups AI Agents Challenge 2025 submission**  
> An AI agent that reads Reddit food posts, analyzes ingredients with Gemini Vision, scores spoilage risk, and generates rescue recipes ordered by urgency — with a Human-in-the-Loop moderation layer before any reply is posted.

[![Live Demo](https://img.shields.io/badge/Live%20Demo-FRACC%20Dashboard-34D399?style=for-the-badge)](https://fracc.34-141-19-206.sslip.io)
[![Python](https://img.shields.io/badge/Python-3.12-blue?style=for-the-badge&logo=python)](https://python.org)
[![Gemini](https://img.shields.io/badge/Gemini-3.5%20Flash-4285F4?style=for-the-badge&logo=google)](https://ai.google.dev)

---

## Problem

Thousands of people post fridge photos on Reddit asking what to cook before things go bad. No tool prioritizes by spoilage risk. Food gets thrown out that could have been saved.

## Solution

An AI agent that:
1. **Reads** Reddit community posts (r/noscrapleftbehind, r/mealprep, r/EatCheapAndHealthy)
2. **Analyzes** ingredients via Gemini 3.5 Flash Vision (detects wilting, discoloration, bruising)
3. **Scores** spoilage risk with a deterministic rule engine (high/medium/low)
4. **Generates** rescue recipes ordered by urgency
5. **Reviews** every draft reply through a Human-in-the-Loop dashboard before posting

---

## Architecture

```
Reddit Posts
    │
    ▼ PRAW stream
Reddit Monitor ──────────────────────────────────────┐
    │                                                 │
    ▼ POST /analyze                                   │
Food Rescue Agent API (FastAPI)                       │
    │                                                 │
    ├─ 1. Intent Detection (keyword scoring)          │
    ├─ 2. Gemini Vision   (ingredient extraction)     │
    ├─ 3. Spoilage Scoring (deterministic rules)      │
    ├─ 4. Rescue Plan     (Gemini text generation)    │
    └─ 5. Draft Reply     (platform-aware format)     │
                │                                     │
                ▼                                     │
         SQLite / PostgreSQL                          │
                │                                     │
                ▼                                     │
       HITL Dashboard (Streamlit)  ◄──────────────────┘
                │
                ▼ Human: Approve / Edit / Reject
         Reddit Reply Posted
```

**Infrastructure:** Docker · Google Cloud Run · Secret Manager · Artifact Registry  
**Auth & Rate Limiting:** .NET 10 ASP.NET Core thin proxy  
**CI/CD:** GitHub Actions

---

## Key Design Decisions

### Hybrid AI + Deterministic Risk Scoring
Gemini Vision is excellent at identifying ingredients and visual condition (wilting, bruising, discoloration). But deciding *what to cook first* cannot be left to a probability. A hardcoded JSON ruleset maps each ingredient to a spoilage window and risk tier. The combination outperformed pure LLM ordering significantly in testing.

### Human-in-the-Loop is Not Optional
Community posts are unpredictable. Every draft reply is reviewed by a human moderator before posting. This is essential for quality, safety, and not embarrassing the bot account in subreddits with strict rules.

### Idempotency Layer
The same Reddit post can hit the pipeline more than once. Every request is deduplicated via an idempotency key in the database before any Gemini call is made.

### Food Safety Disclaimer
Every generated reply includes a hardcoded safety disclaimer. This is not configurable and cannot be removed by prompt injection.

---

## Quick Start

### Prerequisites
- Python 3.12+
- [Gemini Developer API key](https://aistudio.google.com/apikey) (free)
- Docker (optional, for full stack)

### Local (no Docker)

```bash
cd apps/food_rescue_agent
cp .env.example .env
# Edit .env: set GEMINI_API_KEY=your_key_here

pip install -r requirements.txt
uvicorn api.main:app --reload --port 8080
```

Dashboard:
```bash
streamlit run hitl/dashboard.py
```

### Docker (full stack)

```bash
cp .env.example .env  # fill GEMINI_API_KEY
docker compose -f docker-compose.standalone.yml up -d
```

Then open:
- **API:** http://localhost:8080/docs
- **HITL Dashboard:** http://localhost:8501

### Test a rescue request

```bash
curl -X POST http://localhost:8080/analyze \
  -H "X-API-Key: $FOOD_RESCUE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "My avocados are overripe and spinach is wilting. What can I make?",
    "platform": "reddit",
    "context": {"subreddit": "mealprep"}
  }'
```

---

## Project Structure

```
apps/food_rescue_agent/
├── agent/
│   ├── intent.py          # Keyword-based intent classifier
│   ├── vision.py          # Gemini Vision ingredient extraction
│   ├── risk.py            # Deterministic spoilage scoring
│   ├── planner.py         # Gemini rescue plan generation
│   └── genai_client.py    # google-genai v2 SDK wrapper
├── api/
│   ├── main.py            # FastAPI app + endpoints
│   └── models.py          # Pydantic request/response schemas
├── connectors/
│   └── reddit_monitor.py  # PRAW streaming monitor
├── db/
│   └── models.py          # SQLAlchemy ORM (SQLite/PostgreSQL)
├── hitl/
│   └── dashboard.py       # Streamlit HITL review dashboard
├── Dockerfile
├── docker-compose.standalone.yml
└── .env.example
```

---

## Live Demo

**HITL Dashboard:** https://fracc.34-141-19-206.sslip.io  
**API Docs:** https://fracc.34-141-19-206.sslip.io/api/docs

No login required for the demo dashboard.

---

## Technologies

| Layer | Technology |
|-------|-----------|
| AI Vision + Text | Gemini 3.5 Flash via `google-genai` v2 SDK |
| API | FastAPI + Pydantic v2 |
| Dashboard | Streamlit |
| Database | SQLAlchemy 2.x + Alembic · SQLite (dev) · PostgreSQL (prod) |
| Reddit | PRAW |
| Infrastructure | Docker · Google Cloud Run · Secret Manager |
| Auth proxy | .NET 10 ASP.NET Core |
| CI/CD | GitHub Actions |

---

## Findings

**Spoilage prioritization cannot be left to the LLM.** Gemini Vision is great at identifying what is in the fridge, but deciding what to cook first needs deterministic rules, not probabilities. The hybrid approach worked much better than expected.

**The HITL layer was more important than we initially thought.** Community posts are unpredictable and having a human in the loop before posting was essential, both for quality and for not embarrassing ourselves in front of a subreddit.

**The Python and .NET split kept things clean.** .NET handles auth and rate limiting, Python owns the AI pipeline. Keeping that boundary strict paid off.

---

## License

MIT — see [LICENSE](LICENSE)

---

*Built for the Google for Startups AI Agents Challenge 2025*
