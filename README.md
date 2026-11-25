# Failover Chat: LLM chatbot with key failover and response caching

React + FastAPI + SQLite, with LiteLLM handling the key pool and cache.

## 1. Live URLs

- Frontend: `https://04b7e53f52d4b2.app.lhr.life`
- Backend: `https://04b7e53f52d4b2.app.lhr.life` (try `/health`)
- Repo: `https://github.com/akshit1503/lyftr-chatbot`
- Local Frontend: `http://localhost:3000`
- Local Backend: `http://localhost:8000/health`

## 2. Run locally

### Reviewer quick start (about 2 minutes)

You only need Docker and `make`, plus 2 API keys of your own (free Gemini keys: https://aistudio.google.com/apikey). No keys are stored in this repo.

```bash
git clone <this repo> && cd <repo>
make up        # asks for your keys once, writes .env, builds and starts everything
make smoke     # optional: runs the full API contract check (live, cache, failover, 503, 422)
make down
```

Then open http://localhost:3000. Backend: http://localhost:8000/health. Use "Session settings" in the UI to set a system prompt or simulate key failures. No `make`? Run `bash scripts/setup.sh`, then `docker compose up --build`.

**With Docker** (manual): copy `.env.example` to `.env`, set `LLM_API_KEYS`, then `make up`.

**Without Docker:**

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
export LLM_API_KEYS=key1,key2 DATABASE_URL=sqlite:///./app.db ENABLE_FAILURE_SIMULATION=true
uvicorn app.main:app --port 8000
python -m pytest -q       # tests (no network, LLM is mocked)

# frontend (second terminal)
cd frontend
npm install
VITE_API_URL=http://localhost:8000 npm run dev   # http://localhost:3000
```

Environment variables: `LLM_API_KEYS`, `DATABASE_URL`, `ALLOWED_ORIGINS`, `ENABLE_FAILURE_SIMULATION`, plus optional `LLM_MODEL`, `CACHE_TYPE`, `CACHE_DIR`, `DEFAULT_SYSTEM_PROMPT`, `VITE_API_URL` (frontend build time). See `.env.example`.

### Deploying (optional, for maintainers)

`make deploy` runs `scripts/deploy.sh`: backend to Fly.io (Docker, 1 GB volume at `/data`, secrets set from your keys), frontend to Vercel (built against the backend URL), CORS updated to the frontend origin, then the smoke test runs against the live backend. Needs `flyctl`, Node.js and a Fly/Vercel login (the script prompts). Set `FLY_APP`, `FLY_REGION` or `VERCEL_PROJECT` to override defaults.

## 3. Design decisions

**Key fallback.** `llm.generate` walks the key pool in order (`key_1`, `key_2`, ...) and calls `litellm.completion(api_key=...)` for each. Any provider failure (429, quota, 5xx, timeout, empty reply) moves to the next key, and `fallback_attempts` counts the failures. If every key fails the API returns `503 {"detail": "all providers unavailable"}` and nothing is written to history. I used an explicit loop instead of LiteLLM Router so `key_id` and `fallback_attempts` are exact and the simulation hook behaves identically to a real failure. Keys are never logged or returned.

**Caching.** LiteLLM's built-in cache (`Cache(type="local")`, or `disk` via `CACHE_TYPE`) is enabled with `caching=True`. LiteLLM's cache key is the model plus the full message list (system prompt, history, new message), so the same first message in a new session is a hit and any different message is a miss. A hit is detected from LiteLLM's `cache_hit` flag and reported as `LLM_CACHE` with `key_id: null` and `fallback_attempts: 0`; the reply and usage are the stored ones.

**SQLite sessions.** One `messages` table (the required schema, plus an index) and a small `sessions` table for the per-session system prompt. The client sends only the new message; the backend rebuilds the context from SQLite. The user and assistant rows are written in one transaction after a successful reply, so failed requests (422/503) never enter history. The DB path comes from `DATABASE_URL` and lives on the `/data` volume.

**Errors.** Validation errors return 422 with a `detail`, unknown sessions return 404, and a catch-all handler returns a JSON 500 instead of a stack trace.

## 4. Verification

```bash
B=http://localhost:8000
curl $B/health

# live, then cache hit (same first message, new session)
curl -s $B/chat -H 'Content-Type: application/json' -d '{"session_id":"a","message":"What is the capital of France?"}'
curl -s $B/chat -H 'Content-Type: application/json' -d '{"session_id":"b","message":"What is the capital of France?"}'   # LLM_CACHE, key_id null

# failover (use a fresh message; a cached message skips the key pool)
curl -s $B/chat -H 'Content-Type: application/json' -H 'X-Simulate-Failure: key_1=429' -d '{"session_id":"c","message":"Name a prime number"}'   # key_id key_2, fallback_attempts 1

# every key fails
curl -si $B/chat -H 'Content-Type: application/json' -H 'X-Simulate-Failure: *=429' -d '{"session_id":"d","message":"hello"}'   # 503

curl $B/sessions/a/messages
```

`make smoke` (or `bash scripts/smoke.sh <base-url>`) checks all of this automatically.

In the UI, each reply shows source, model, latency and per-request input/output tokens. Open "Session settings" to set a system prompt or pick a simulated failure. Tests: `make test`.

## 5. Setup used

- Editor: `<your editor>`
- AI tools: Claude (scaffolding, tests, review), LiteLLM docs

## 6. Bonus features

- Per-session system prompt field in the UI
- Failure simulation picker in the UI (sends `X-Simulate-Failure`)
- Optional disk cache (`CACHE_TYPE=disk`)
- Backend test suite covering cache, failover, 503, validation and session isolation
