# CulinaAI Food Rescue Agent

Python FastAPI service — food rescue pipeline for the Google AI Agents Challenge 2026.

## Architecture

```
Input (Telegram / Manual Upload / .NET Proxy)
  → Intent Detection (pure Python, rule-based)
  → Vision Analysis  (Gemini Vision, if images present)
  → Risk Engine      (JSON rules, no API call)
  → Rescue Planner   (Gemini Pro)
  → Reply Generator  (platform templates)
  → HITL Queue       (SQLite)
  → Streamlit Dashboard (approve / edit / reject)
```

## Setup

```bash
cp .env.example .env
# fill in GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, FOOD_RESCUE_API_KEY

pip install -r requirements-dev.txt
```

## Run locally

```bash
uvicorn api.main:app --reload --port 8080
streamlit run hitl/dashboard.py --server.port 8501
python connectors/telegram_bot.py  # or via webhook
```

## API

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | /health | none | Health check |
| POST | /analyze | X-API-Key | Full analysis (text + images) |
| POST | /analyze/text | X-API-Key | Text-only fast path |
| GET | /metrics | X-API-Key | Processing stats |

### POST /analyze

```json
{
  "text": "Spinach going bad today, no freezer",
  "images": ["<base64>"],
  "platform": "telegram",
  "context": { "no_freezer": true, "people_count": 3 },
  "idempotency_key": "optional-dedup-key"
}
```

## Tests

```bash
# Unit tests (no API calls, fast)
pytest tests/unit/ -v

# Integration tests (TestClient, mocked Gemini)
pytest tests/integration/ -v

# With real Gemini API
GEMINI_INTEGRATION=true GEMINI_API_KEY=<key> pytest tests/integration/ -v
```

## Security

- Agent is **not public-facing** — internal VPC / Cloud Run internal ingress only
- No raw images stored in DB — temp files deleted after each request
- Usernames/PII never enter logs or model prompts
- HITL approval required before any community reply is sent
- Food safety disclaimer injected in every response — cannot be omitted

## Disclaimer policy

Every response includes:

> ⚠️ These are general cooking suggestions only. Verify freshness by sight and smell.
> Storage conditions and temperature history are unknown to us — you make the final
> food safety call. When in doubt, throw it out. CulinaAI is not liable for food safety decisions.
