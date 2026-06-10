# CulinaAI Food Rescue Agent

Python FastAPI service — food rescue pipeline for the Google AI Agents Challenge 2026.

## Architecture

**Primary channel: Reddit.** A long-running monitor streams target subreddits, filters
for food-rescue intent, and pushes posts through the pipeline into a human-moderated queue.
Telegram / manual upload are secondary inputs.

```
Reddit monitor (subreddit stream)  ─┐
Telegram / Manual Upload           ─┤→ POST /analyze
                                     │
  → Intent Detection (pure Python, rule-based)
  → Vision Analysis  (Gemini Vision, if images present)
  → Risk Engine      (JSON rules, no API call)
  → Rescue Planner   (Gemini)
  → Reply Generator  (platform templates)
  → HITL Queue       (SQLite)
  → Streamlit Dashboard (approve / edit / reject)
        └─ approve → reply posted back to Reddit (gated by REDDIT_POST_ENABLED)
```

### Reddit channel & posting safety

The Reddit reply loop is **closed**: monitor → `/analyze` → HITL queue → moderator
approve/edit → comment posted to the source thread. Auto-posting is **off by default**
(`REDDIT_POST_ENABLED=false`): approving logs the decision and shows the reply for the
moderator to copy manually — protecting the bot account from subreddit-rule / anti-spam
bans. Flip to `true` only once the bot account and subreddit rules are cleared (a private
test subreddit is recommended first).

## Setup

```bash
cp .env.example .env
# fill in GEMINI_API_KEY, FOOD_RESCUE_API_KEY, and the Reddit creds:
#   REDDIT_CLIENT_ID / SECRET / USERNAME / PASSWORD  (create a "script" app at
#   https://www.reddit.com/prefs/apps), REDDIT_SUBREDDITS, REDDIT_POST_ENABLED=false

pip install -r requirements-dev.txt
```

## Run

### Docker Compose (all 3 processes — recommended)

```bash
# from repo root, with the food_rescue_agent override:
docker compose -f apps/food_rescue_agent/docker-compose.override.yml up --build
#   food-rescue-agent  → FastAPI pipeline (internal)
#   reddit-monitor     → streams subreddits → /analyze
#   hitl-dashboard     → Streamlit moderation UI at http://localhost:8501
```

### Locally (separate terminals)

```bash
uvicorn api.main:app --reload --port 8080         # API
streamlit run hitl/dashboard.py --server.port 8501 # HITL dashboard
python connectors/reddit_monitor.py                # Reddit monitor (primary)
python connectors/telegram_bot.py                  # Telegram (secondary, optional)
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
  "platform": "reddit",
  "context": { "no_freezer": true, "people_count": 3 },
  "idempotency_key": "reddit:<post_id>",
  "source_metadata": { "subreddit": "noscrapleftbehind", "reddit_post_id": "<id>" }
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
- Reddit auto-posting is **off by default** (`REDDIT_POST_ENABLED=false`) — dry-run / manual copy
- Food safety disclaimer injected in every response — cannot be omitted

## Disclaimer policy

Every response includes:

> ⚠️ These are general cooking suggestions only. Verify freshness by sight and smell.
> Storage conditions and temperature history are unknown to us — you make the final
> food safety call. When in doubt, throw it out. CulinaAI is not liable for food safety decisions.
