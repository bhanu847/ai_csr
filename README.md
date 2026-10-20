# AI Workforce Platform

An AI voice customer-service platform for healthcare/PBM (pharmacy benefit manager) support. Callers talk to an AI agent over a real phone call; the AI answers from your uploaded documents, looks up real member/claim/pharmacy data, hands off between specialist agents, and everything is recorded, scored, and analyzable afterward.

This document covers: how it's built, what database it uses, how each feature works and where its data comes from/goes, what it costs to run, how to run it locally, and how to deploy it for a real phone number. For a pure checklist of accounts/keys/software, see [`SETUP.md`](SETUP.md). For what's actually been proven to work versus what's built-but-unverified, see [§12](#12-pbm-data-architecture) and [§13](#13-evaluation--validation-framework), and `docs/validation/evidence_requirements.md` — this project tracks every capability claim as `VERIFIED` / `BUILT-UNVERIFIED` / `NOT IMPLEMENTED` / `UNKNOWN`, on purpose, rather than describing everything as if it were finished.

---

## 1. Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.14, FastAPI, SQLAlchemy 2.0, Alembic (migrations) |
| Database | **PostgreSQL** with the **pgvector** extension (for semantic search) |
| Frontend | Angular 21 (standalone components, signals) |
| Voice | Twilio (phone number + real-time audio streaming over WebSocket) — a paid piece |
| LLM | **Ollama**, self-hosted, free — conversational replies, call summaries, QA scoring, intent routing |
| Speech-to-text | **faster-whisper**, self-hosted, free, CPU |
| Text-to-speech | **piper-tts**, self-hosted, free, CPU |
| Embeddings | **Ollama**, self-hosted, free — `nomic-embed-text`, used for the knowledge-base/RAG search |
| Auth | JWT (PyJWT), bcrypt password hashing, per-IP rate limiting on auth endpoints |

**On being fully self-hosted again.** This app started fully self-hosted, moved chat + speech to Azure for a stretch (hosted services are easier to get acceptable quality/latency out of without tuning), and has now moved back to self-hosted for all three — no per-call network hop, no per-token/per-minute cloud billing, and (§13) a fast instant-answer path for common questions that bypasses the LLM entirely. The tradeoff that motivated the Azure move hasn't vanished: a self-hosted model's tool-calling/grounding fidelity and Piper's voice naturalness are genuinely different from a large hosted model's, and that difference is **BUILT-UNVERIFIED, not yet measured**, under this specific setup (`qwen3:1.7b` via Ollama — the default model size itself is also a measured latency tradeoff on CPU-only hardware, see `FAQ.md` §1) — see `docs/validation/evidence_requirements.md`. Swapping back is a deliberate bet on speed/cost/independence; it is not yet backed by a real-call comparison, and on CPU-only hardware without a GPU, "speed" specifically means picking a small enough model to be workable at all, not a guaranteed win over the previous hosted setup.

Twilio remains unavoidable for a different reason: getting a real phone number that a caller can dial, and having that call reach your server, always goes through the public telephone network (PSTN) — there is no open-source way around that.

**Why PostgreSQL specifically, not "a database" in the abstract**: two features depend on Postgres-specific capabilities and won't work on MySQL/SQLite/etc. without rework —
1. **pgvector** stores document-chunk embeddings and does the cosine-similarity search that powers the knowledge base and confidence scoring.
2. **Row-Level Security (RLS)** enforces multi-tenant data isolation *inside the database itself* — every tenant-owned table has a policy like `tenant_id = current_setting('app.current_tenant_id')::uuid`, so even a bug in application code can't leak one business's data into another's. This is set up by the app's own migrations, not manual DBA work.

---

## 2. Database

One PostgreSQL database, two roles:

- **`app_user`** — what the running app connects as. Low-privilege: only the grants each table needs (`SELECT/INSERT/UPDATE/DELETE` for mutable tables like `agents`/`calls`; `SELECT/INSERT` only — no update or delete — for append-only tables like `conversation_messages`, `tool_execution_logs`, `audit_logs`, so a transcript can never be quietly edited after the fact).
- **`postgres`** (or another owner/superuser role) — used only by Alembic to run migrations (create tables, roles, grants, RLS policies). Never used by the running app.

This is why `backend/.env` has **two** connection strings: `DATABASE_URL` (runtime, `app_user`) and `MIGRATIONS_DATABASE_URL` (migrations, superuser).

### Tables, grouped by what they're for

| Group | Tables |
|---|---|
| Platform / tenancy | `tenants`, `users`, `audit_logs` |
| Agent configuration | `agents` (persona, voice, department), `knowledge_documents`, `knowledge_chunks` (pgvector embeddings) |
| Call records | `calls`, `conversation_messages`, `tool_execution_logs`, `appointments` |
| Customer memory | `customer_profiles` |
| Healthcare/PBM data | `members`, `claims`, `drugs` (formulary), `pharmacies`, `tickets` |
| Automation | `workflows`, `workflow_steps` |
| Analysis | `training_insights` |

Every table except `tenants` (which has no tenant context yet — it's how a tenant gets resolved in the first place) and the append-only log tables enforces RLS. Migration history lives in `backend/alembic/versions/`, applied in order, each one additive (nothing in this project has ever rewritten or dropped existing data).

---

## 3. How a phone call actually works (the core loop)

```
Caller dials your Twilio number
        │
Twilio → POST /api/twilio/incoming
        ├─ looks up which tenant owns this number
        ├─ finds/creates a CustomerProfile for the caller's phone number
        ├─ creates a Call row (status = in_progress)
        └─ replies with TwiML telling Twilio to open a WebSocket
        │
Twilio opens WebSocket → /media-stream
        ├─ loads the agent (persona, voice, department)
        ├─ loads customer memory + this department's active Workflows
        ├─ builds the system prompt (persona + rules + memory + workflows)
        └─ speaks a greeting (Piper TTS) — by name, if the caller is known
        │
Caller speaks (repeats every turn)
        ├─ voice activity detection buffers audio until the caller pauses
        ├─ if the caller starts talking WHILE the AI is still speaking,
        │   sustained speech (200ms+) triggers a barge-in: Twilio is told
        │   to clear the AI's queued audio immediately, and the caller's
        │   new utterance is captured from the moment it started
        ├─ faster-whisper transcribes the utterance
        ├─ an instant-answer classifier checks first: a confident match on a
        │   common, non-personalized question (e.g. "how does prior auth
        │   work?") answers directly in ~1ms, no LLM call — anything about a
        │   specific member/claim/benefit, or anything it's not confident
        │   about, falls through to the LLM below unchanged
        ├─ (first utterance only) intent router may hand the call off to
        │   a specialist agent (Claims / Pharmacy / Benefits / ...)
        ├─ the LLM (Ollama) gets the conversation + available tools, and
        │   either replies directly or calls a tool — e.g. verify_member,
        │   check_claim_status, search_documents, find_pharmacy
        ├─ tools query Postgres directly (Members/Claims/Drugs/Pharmacies/
        │   your uploaded documents' embedded chunks)
        ├─ every message and tool call is saved (conversation_messages,
        │   tool_execution_logs) — this is what the Conversations page shows
        └─ Piper TTS speaks the reply back over the same WebSocket
        │
Call ends → Twilio → POST /api/twilio/status
        ├─ Call marked completed
        ├─ an LLM call summarizes it (intent, sentiment, resolution)
        └─ a second LLM call scores it (accuracy/compliance/empathy/resolution)
```

Everything below either **feeds this loop** (customer memory, workflows) or **reads what this loop already wrote** (dashboards, analytics, training insights) — nothing duplicates the call pipeline.

---

## 4. Features

### Core voice pipeline
Real-time Twilio audio ↔ faster-whisper (STT) / piper-tts (TTS) ↔ a self-hosted LLM via Ollama, with a multi-round tool-calling loop (the model can call several tools in sequence before replying) and barge-in support (below). Common, non-personalized questions are intercepted before the LLM by a small trained classifier (§4 "Instant-answer fast path") instead of always paying an LLM round trip. This is the foundation everything else plugs into.

### Instant-answer fast path
A tiny TF-IDF + logistic-regression classifier (`app/fastpath/`, trained offline into `models/instant_answer.joblib`) checks every caller utterance before the LLM/tool loop runs. It only ever answers **static, non-personalized FAQ facts** (prior-authorization process, generic vs. brand drugs, mail-order program, specialty medication program, appeals process, out-of-network pharmacy use — sourced from the uploaded PBM FAQ) plus a few conversational intents (greeting, thanks, goodbye, "connect me to a human"). Anything shaped like a real member/claim/benefit/verification question is in its training data as an explicit **out-of-scope** example, specifically so the classifier learns to *not* intercept it and instead falls through to the normal tool-calling path — it never has access to tool results or personalized data, so a wrong instant answer is a knowledge-accuracy slip, not a PHI-safety one. It only answers above a cross-validation-calibrated confidence threshold (95% target instant-answer precision by default); anything less confident goes to the LLM exactly as before.

### Barge-in / interruption handling
While the AI's reply is playing, the handler keeps watching the caller's audio — not by transcribing continuously, but by checking every incoming frame's loudness. 200ms of sustained speech is treated as a genuine interruption (a click, cough, or brief noise isn't); on trigger, Twilio is told to clear the AI's queued audio immediately, and the caller's new utterance starts from the exact audio that triggered it, so they never have to repeat themselves. The loudness bar during AI playback is set higher than during normal turn-taking, specifically because a caller on speakerphone can have the AI's own voice leak back into their mic as echo — the higher bar makes that leaked echo less likely to falsely trigger a cutoff than genuine direct speech. Tunable via `BARGE_IN_MS`/`BARGE_IN_RMS_THRESHOLD` without a code change.

### Knowledge base / RAG
Upload PDFs or DOCX per agent (Agent Studio → an agent's page). Documents are parsed, split into chunks along paragraph boundaries (not a blind word-count window, which can cut a sentence in half), embedded (`nomic-embed-text` via Ollama, using the task-specific prefixes that model expects for indexed text vs. a search query), and stored in `knowledge_chunks` with a pgvector column. When the AI needs facts, it searches by cosine similarity against the caller's question.

### Confidence Engine
Every knowledge lookup gets a 0–100 score from how close the best-matching chunk is. **≥90% → answered normally. 70–89% → answered but hedged, source named. <70% → the source text is withheld entirely** — the model isn't just told to be careful, it literally never receives text it wasn't confident enough to trust. Scores are stored per-message (`conversation_messages.confidence_score`) and shown as a color-coded badge in the transcript. *(The 90/70 thresholds haven't been re-validated against `nomic-embed-text`'s actual distance distribution — worth watching once real call volume exists.)*

### Citations
Every knowledge-grounded reply records which document/page it came from (`conversation_messages.citations`), shown as chips under the message in the transcript — visible to a supervisor, never read aloud on the call.

### Customer 360 Memory
Callers are recognized by phone number (`customer_profiles`). Returning callers get greeted by name, and the AI gets a short internal briefing on prior calls (intent + resolution only) — with a hard rule never to recite medical/claims specifics until identity is re-confirmed *in that call*.

### PBM / healthcare tools
`verify_member`, `check_claim_status`, `get_benefits`, `search_formulary`, `find_pharmacy`, `create_ticket`, `schedule_callback`, `send_email`, `update_customer`, plus `search_documents`, `schedule_appointment`, `escalate_to_human`. Claim/benefit lookups are hard-gated behind `verify_member` (member ID + DOB + ZIP) — no PHI is revealed pre-verification. The five PBM-data tools (`verify_member`/`check_claim_status`/`get_benefits`/`search_formulary`/`find_pharmacy`) sit behind a provider interface, not hardcoded Postgres queries — see [§12](#12-pbm-data-architecture). Seed sample data with `backend/scripts/seed_pbm_data.py`. (`send_email` currently only records the intent to an audit log — no email provider is wired up yet; see [§11 Known gaps](#11-known-gaps-by-design-not-oversight).)

### Multi-Agent routing
Configure multiple agents with a `department` (Agent Studio). On a caller's first utterance, an intent classifier decides whether to hand off from the general agent to a specialist — invisibly, mid-call, keeping the transcript intact. Each department only gets its own relevant tools.

### Workflow Engine
Admin-defined procedures ("Workflows" page): a name, a trigger description, and an ordered list of tools to call. Active workflows for the current department get injected into the system prompt as a mandatory sequence. (Not a drag-and-drop canvas — an ordered step list with reorder buttons, which does the same job.)

### Call summaries & QA scoring
After every call: one LLM pass writes `summary`/`intent`/`sentiment`, a second scores `accuracy`/`compliance`/`empathy`/`resolution` (0–100 each) with reviewer notes — visible in the Conversations transcript drawer.

### Conversations page
Every call's full transcript (customer/assistant bubbles + tool-execution cards), searchable/filterable list, resolution/sentiment badges.

### Customers page
Every caller ever seen, with call history and derived sentiment — nothing stored twice; it's a live join over `calls`, not a duplicated table.

### Dashboard & Analytics
Dashboard: active calls, resolution rate, estimated cost saved (explicitly labeled as an *estimate*, not accounting), recent conversations. Analytics: top intents, sentiment mix and its trend over time, resolution trend over time — all computed live from `calls`, nothing precomputed or faked.

### AI Training Center
On demand ("Run analysis" button), scans recent low-confidence answers, escalations, and low-QA calls for **recurring patterns** (not one-offs) and suggests: upload this document / adjust this behavior / fix this process gap. Insights are saved so a supervisor can acknowledge or dismiss them.

### Live Operations (Supervisor Command Center)
Live list of in-progress calls (polls every 4s), each call's most recent turn and confidence. A supervisor can:
- **Monitor** — open the live transcript (same drawer as Conversations, refreshes as new turns come in)
- **Stop AI** — the AI immediately stops generating replies and gives a holding line instead, until resumed
- **Send suggestion** — a note that gets folded into the AI's *next* reply only, then discarded

**Not implemented: Join call / Transfer call.** Both need real Twilio conference/audio-bridging, which needs a live phone call to test against — I didn't ship code I couldn't verify actually works.

---

## 5. Security

- **Password reset** — `/api/auth/forgot-password` and `/api/auth/reset-password`. A reset token is generated and only its SHA-256 hash is stored (never the raw token), with a 30-minute expiry; the forgot-password response is identical whether or not the account exists, so the endpoint can't be used to enumerate registered emails.
- **Rate limiting** — per-IP, on every auth endpoint: login (10/min), register-tenant (5/hour), forgot-password (3/hour), reset-password (10/hour). Protects against brute-force login attempts and registration spam.
- **`JWT_SECRET` validated at startup** — the app refuses to start if it's still the `.env.example` placeholder or under 32 characters, so a weak secret can never silently ship.
- **`.env` is gitignored and has never been committed** — verified, not assumed.

**Known limitation:** no email provider is wired up anywhere in this app yet, so the password-reset token isn't actually emailed to the user — it's written to the audit log for a human/future integration to pick up (the same limitation the `send_email` tool already has). A genuine self-service reset needs a real email provider (SendGrid, Resend, SMTP, ...), which is a provider/cost decision, not a code change.

---

## 6. Concurrency & scaling

Two different kinds of limits apply here, and they need different fixes:

**Code-level ceilings (fixed):** the DB connection pool and the shared thread pool for blocking work (every STT/LLM/TTS/DB call in a turn runs via `asyncio.to_thread`) both had small, accidental defaults — 15 DB connections and ~12 threads on an 8-core box. Both are now configurable (`DB_POOL_SIZE`/`DB_POOL_MAX_OVERFLOW`, `BLOCKING_THREAD_POOL_SIZE`) and raised well past those defaults. This removes an artificial throttle; it does **not** by itself mean the app can handle a specific number of concurrent calls.

**Real capacity ceilings (infrastructure, not code):** actual concurrency is now bounded by local hardware — how many concurrent faster-whisper transcriptions and Ollama chat completions your machine/GPU can actually run before they start queuing behind each other for CPU/GPU time — plus Twilio's account-level concurrent-call limit (raised via a support request, not code), a single `uvicorn` process being one Python event loop, and Postgres's own `max_connections`. None of this is provable from code review — it needs real load testing on real hardware before you can honestly claim a specific concurrent-call number. For real scale, the app tier itself can scale horizontally (multiple stateless backend instances behind a WebSocket-capable load balancer); Ollama/faster-whisper/piper-tts capacity is now a matter of your own hardware budget rather than a cloud quota.

---

## 7. Cost

One real per-usage cost (Twilio), everything else self-hosted and free to run (not free to own —
it costs whatever hardware you run Ollama/faster-whisper/piper-tts on):

| Component | Basis | Approx. cost |
|---|---|---|
| **Twilio** | Phone number rental + inbound voice + Media Streams | ~$1–2/month + ~$0.0125/min |
| **Ollama (LLM + embeddings)** | Self-hosted | $0 cloud cost — local CPU/GPU time |
| **faster-whisper (STT)** | Self-hosted | $0 cloud cost — local CPU time |
| **piper-tts (TTS)** | Self-hosted | $0 cloud cost — local CPU time |

There's no per-token or per-minute cloud bill for the LLM or speech pieces anymore — the real
cost is the machine running them, and its ceiling is how many concurrent calls that hardware can
actually serve (see [§6](#6-concurrency--scaling)), not a rate card.

**Compared to a human CSR:** this app's own dashboard already assumes $12/human-handled call (`ASSUMED_COST_PER_HUMAN_CALL` in `dashboard.py`, explicitly labeled there as a stated assumption, not measured accounting). At a ~5-minute average handle time that's roughly $2.40/minute for a human agent — against $0 in marginal per-call cloud cost for a self-hosted AI call (Twilio's per-minute fee aside), that gap is even starker than it was under hosted LLM/speech pricing. The honest framing isn't "AI replaces humans" — it's "AI absorbs the high-volume, well-defined majority of calls at a fraction of the per-minute cost, and hands the genuinely hard ones to `escalate_to_human`," which is exactly how the confidence thresholds and escalation tool are architected, not an accident.

---

## 8. Running it locally

**Prerequisites**: Python 3.14, Node.js + npm, PostgreSQL with the `pgvector` extension available, [Ollama](https://ollama.com) installed and running, Piper voice model files downloaded, a Twilio account (for real calls — not required just to browse the dashboard). See [`SETUP.md`](SETUP.md) for the full account/key checklist.

### Install Ollama and pull the models

```bash
# https://ollama.com/download
ollama pull nomic-embed-text    # embedding model
ollama pull qwen3:1.7b          # chat model — conversational replies + tool-calling (see FAQ.md §1 for measured latency/model-size tradeoffs on CPU-only hardware)
ollama serve                    # runs on http://localhost:11434 (often already running as a service)
```

Set `OLLAMA_KEEP_ALIVE=-1` (or a long duration like `24h`) as an environment variable on the
Ollama process/service itself — its OpenAI-compatible endpoint (which this app uses) drops a
per-request `keep_alive`, so without this the model unloads after ~5 minutes idle and the next
call pays a multi-second cold-start reload.

### Download Piper voices

Piper needs actual voice model files (`<voice-name>.onnx` + `<voice-name>.onnx.json`), not
bundled in this repo. Download the ones you plan to use from the
[Piper voices collection](https://huggingface.co/rhasspy/piper-voices) into `backend/voices/`
(e.g. `en_US-amy-medium`, `en_US-ryan-medium`, `en_GB-alan-medium`, `hi_IN-rohan-medium` — these
specific names are what existing agents already have stored in `voice`).

### Backend

```bash
cd backend
python -m venv venv
venv/Scripts/activate          # venv\Scripts\activate.bat on plain cmd
pip install -r requirements.txt
```

Create `backend/.env` (see `backend/.env.example` for the full annotated template — every variable, required or not, is documented there):

```
DATABASE_URL=postgresql+psycopg://app_user:CHANGE_ME@localhost:5432/ai_workforce
MIGRATIONS_DATABASE_URL=postgresql+psycopg://postgres:CHANGE_ME@localhost:5432/ai_workforce
JWT_SECRET=<long random string, 32+ chars>
LLM_MODEL=qwen3:1.7b
LLM_DISABLE_THINKING=true
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIM=768
PIPER_VOICES_DIR=./voices
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
PUBLIC_SERVER_URL=...           # see deployment section — must be a real public HTTPS URL to take real calls
CORS_ORIGINS=http://localhost:4200
```

Run migrations, train the instant-answer fast path, then start the API:

```bash
alembic upgrade head
python train_instant_answer_model.py   # optional -- see §4 Instant-answer fast path
uvicorn app.main:app --port 8001 --reload
```

(Optional) seed sample PBM data so the healthcare tools have something to look up:

```bash
python scripts/seed_pbm_data.py <your-tenant-slug>
```

### Running tests

```bash
cd backend
venv/Scripts/activate
python -m pytest tests/
```

These are integration tests against a real (throwaway, self-cleaning) tenant in your configured Postgres — `DATABASE_URL`/`MIGRATIONS_DATABASE_URL` must point at a real, migrated database, same as running the app. See [§12](#12-pbm-data-architecture) and [§13](#13-evaluation--validation-framework) for what these tests do and don't prove.

### Frontend

```bash
cd frontend
npm install
npm start          # serves on http://localhost:4200, proxies API calls to localhost:8001
```

Register, log in, and you're in the dashboard.

---

## 9. Deploying for real phone calls

This is the part that trips people up: **adding API keys alone does not connect a phone number.** Several things have to line up.

### Step 1 — Host the backend somewhere with a public HTTPS URL
`localhost` is not reachable by Twilio's servers. Options:
- **Quick test**: `ngrok http 8001` while running locally — gives you a temporary public HTTPS URL.
- **Real deployment**: any host that can run the FastAPI app behind HTTPS (a VM, a container platform, etc.) with a real domain.

Whatever URL you end up with, set it as `PUBLIC_SERVER_URL` in `backend/.env`. It's used two ways: as the Twilio webhook base, and (converted to `wss://`) as the live audio WebSocket URL.

### Step 2 — Buy and configure a Twilio number
On a trial account you'll need to add a payment method before you can buy a number — Console → Billing → Payment Methods, then Phone Numbers → Buy a number (make sure Voice capability is checked). On the number:
- **Voice webhook** → `POST https://<your-public-url>/api/twilio/incoming`
- **Status callback** → `POST https://<your-public-url>/api/twilio/status`

### Step 3 — Register the number in your database
`tenants.twilio_phone_number` must exactly match the Twilio number (E.164 format, e.g. `+15551234567`) — that's how an incoming call is matched to a tenant and its default agent. There's no admin UI for this yet; it needs a direct row insert/update, e.g.:

```sql
UPDATE tenants SET twilio_phone_number = '+15551234567' WHERE slug = 'your-tenant-slug';
```

### Step 4 — Host the frontend
Build with `npm run build` in `frontend/`, serve the `dist/frontend` output from any static host, and point it at your deployed backend's URL (currently hardcoded to `http://localhost:8001` in each Angular service — for a real deployment these need to point at your backend's public URL instead).

### Step 5 — Deploy Postgres
A managed Postgres with the `pgvector` extension enabled (most managed providers support installing it) — run the same `alembic upgrade head` against it once, using `MIGRATIONS_DATABASE_URL` pointed at the production database.

Once all five are in place, dialing the number really does ring through to the AI — that path is real, not a demo stub.

---

## 10. Using the application

1. **Register/log in** — first user in a tenant becomes its admin.
2. **Agent Studio** — create an AI agent: name, voice, persona, department (leave as "general" unless you're setting up multi-agent routing). Voice is any Piper voice name you've downloaded into `backend/voices/` (e.g. `en_US-amy-medium`) — see the [Piper voices collection](https://huggingface.co/rhasspy/piper-voices). Upload PDFs/DOCX to give it a knowledge base.
3. **Set a default agent** — the tenant's default agent answers calls until a specialist is routed to.
4. **(Optional) PBM data** — run the seed script, or insert real `members`/`claims`/`drugs`/`pharmacies` rows for your own data.
5. **(Optional) Workflows** — define step-by-step procedures for specific request types.
6. **(Optional) Multiple departments** — create more agents with different `department` values (claims/pharmacy/benefits/provider/escalation) to enable automatic routing.
7. **Go live** — follow the deployment steps above, call the number.
8. **Watch it work**:
   - **Live Operations** — see the call while it's happening, pause the AI, or send it a live suggestion.
   - **Conversations** — after the call, read the full transcript with citations and confidence.
   - **Customers** — see that caller's history.
   - **Dashboard / Analytics** — aggregate trends, including sentiment over time.
   - **AI Training Center** — click "Run analysis" periodically to surface patterns worth fixing (missing docs, prompt issues).

---

## 11. Known gaps (by design, not oversight)

- **No live audio join/transfer** for supervisors (Live Operations) — needs real Twilio conference work, untested here.
- **No drag-and-drop workflow canvas** — workflows are an ordered step list, functionally equivalent, not visually a node graph.
- **No admin UI yet** for registering a tenant's Twilio number — direct DB access required.
- **Frontend API URLs are hardcoded** to `localhost:8001` — needs an environment-based config swap before a real multi-environment deployment.
- **"Cost saved" on the dashboard is a stated estimate** (`resolved calls × assumed cost/call`), not real accounting.
- **Claim `PENDING` status has no stored reason** — only rejected claims have a `rejection_reason`; the AI can say a claim is pending but not yet explain *why*.
- **No email provider wired up** — password reset and the `send_email` tool both stop at "recorded, not delivered" (see [§5 Security](#5-security)).
- **No billing/monetization layer** — no Stripe or usage-based plan enforcement for your own customers; Twilio's per-minute cost is what a tenant's calls cost *you*, with no built-in way to charge them for it (the LLM/STT/TTS pieces are self-hosted and have no per-call cloud cost).
- **No platform admin console** — onboarding a tenant's Twilio number needs a raw SQL update (Step 3 above), not a UI.
- **Real concurrent-call capacity is unverified** — the code-level thread/connection-pool ceilings are fixed, but actual throughput depends on local hardware capacity for Ollama/faster-whisper and Twilio account limits, and hasn't been load-tested (see [§6](#6-concurrency--scaling)).
- **Confidence thresholds (90/70) aren't re-validated** for the current embedding model — see [§4 Confidence Engine](#confidence-engine).
- **Local LLM tool-calling fidelity against the self-hosted model (`qwen3:1.7b` via Ollama, thinking disabled) hasn't been measured against real PBM scenarios** — see [§13](#13-evaluation--validation-framework). The multi-round tool loop (`app/conversation/agent.py`) assumes OpenAI-style tool-calling behavior; Qwen3 supports it, but accuracy under this project's specific prompts/tools, at this model size, with thinking disabled, is unverified. `qwen3:1.7b` was chosen for CPU latency (`qwen3:8b` measured ~140–150s/call on this project's dev hardware — see `FAQ.md` §1), not for tool-calling quality, which is an explicit open tradeoff.
- **The instant-answer fast path (§4) only ever answers static FAQ facts and generic conversational intents** — anything in `app/fastpath/data/faq_intents.json`'s `out_of_scope_examples` (every claims/benefits/formulary/pharmacy-lookup/verification-shaped question) is trained to fall through to the LLM, by design — but that training data is small and hand-written, not validated against a large held-out set of real caller phrasings.
- **One real end-to-end smoke test (not a scenario, just a sanity check) surfaced a concrete quality gap**: asked "what's my claim status" with no prior verification, `qwen3:1.7b` correctly declined to reveal any claim data (the safety property held), but asked for a claim number instead of following the system prompt's actual instruction to request member ID/DOB/ZIP for verification first — a real, observed instruction-following miss at this model size, not a hypothetical one. That same real turn (full system prompt + all 11 tool schemas for the "general" department) took ~81 seconds on this project's CPU-only dev hardware — notably worse than the ~15-19s measured on short synthetic prompts (FAQ.md §1), because prompt processing time scales with the much longer real system prompt + tool-schema payload, not just the reply length.
- **No sentence-by-sentence streaming exists anywhere in the voice pipeline** (not STT, not the LLM, not TTS) — every turn waits for a complete transcript, then a complete LLM reply, then complete synthesized audio, before anything is sent back. This is the single biggest further latency lever and was deliberately left out of this pass (it needs `media_stream_handler.py`'s per-reply mark/barge-in tracking reworked to per-sentence marks, and handling a tool call that interrupts a stream mid-sentence) — see `FAQ.md` §1.
- **No real PBM/healthcare-system integration exists.** `members`/`claims`/`drugs`/`pharmacies` are seeded development data, not a connection to any real claims/eligibility/formulary system. The tool layer is built to make a real integration a swappable adapter rather than a rewrite — see [§12](#12-pbm-data-architecture) — but no such adapter has been written, because no real external system has been connected to yet.
- **No domain-validated evaluation results exist.** The evaluation framework (`app/evaluation/`) is tested and confirmed to work mechanically, but every scenario it's been run against so far is a small, hand-written fixture set that exists to prove the harness works — not a healthcare/PBM expert's assessment of real call correctness. See [§13](#13-evaluation--validation-framework).

---

## 12. PBM data architecture

**Status: interface + seeded adapter VERIFIED (automated tests). Real external integration NOT IMPLEMENTED.**

The five PBM-data tools (`verify_member`, `check_claim_status`, `get_benefits`, `search_formulary`, `find_pharmacy`) don't embed SQL directly. They call a `PBMProvider` interface (`app/pbm/provider.py`) — plain-data records (`MemberRecord`, `ClaimRecord`, `FormularyEntry`, `PharmacyRecord`), not SQLAlchemy models — so the tool/agent layer never knows or needs to know whether the data behind it is the seeded Postgres tables, a REST API, a FHIR server, or a real customer's claims platform.

Two implementations exist:
- `PostgresPBMProvider` (`app/pbm/postgres_provider.py`) — the seeded dev/test data described in §3/§4. This is the **only** backend this project has today; it is a development fixture, not a PBM integration.
- `MockPBMProvider` (`app/pbm/mock_provider.py`) — a fixed in-memory fake with zero Postgres dependency, used only in `backend/tests/pbm/test_substitutability.py` to prove the tool layer genuinely depends on the interface, not on Postgres specifically.

**What's actually been tested** (`backend/tests/pbm/`, 18 tests): the seeded adapter produces correct results against a real throwaway tenant (verification success/failure, claim ordering and filtering, benefits data, formulary search, in-network pharmacy filtering); the same unmodified tool-handler code works correctly against `MockPBMProvider`; the identity-verification gate on PHI-protected tools holds regardless of which provider is plugged in.

**What that does and doesn't prove:** it proves the *boundary* is real — a third, real-system-backed implementation can be written without touching `app/tools/handlers.py`. It says nothing about whether a real external system fits this exact interface shape without changes (pagination, retries, richer error handling, etc. may all differ from a real system's needs), because no real integration has been attempted yet.

## 13. Evaluation & validation framework

**Status: harness mechanics VERIFIED. Domain/accuracy validation UNKNOWN — no real scenarios have been run.**

`app/evaluation/` is a framework for scoring the AI's behavior against defined expected outcomes: `schema.py` (scenario/expected-behavior/observed-behavior data model), `scoring.py` (five dimensions — tool selection, answer content, escalation, verification gating, technical reliability), `runner.py` (`RealPipelineExecutor`, which drives a scenario through the actual conversation pipeline and reads results back from `tool_execution_logs` — the same persistence path a real call already writes to), `report.py` (aggregation and text/JSON reporting), `scenario_loader.py` (parses a domain expert's JSON scenario file into the same schema).

**What's actually been tested** (`backend/tests/evaluation/`, 19 tests): the scorer correctly passes scenarios that meet their expectations *and* correctly fails ones that don't (verified with a deliberately-scripted failure case, not just happy-path scenarios); aggregation and reporting produce correct counts; the framework structurally refuses to summarize test-fixture results and real-scenario results together (`MixedFixtureAndRealResultsError`); the scenario loader correctly parses a valid file and rejects malformed ones with clear errors.

**What that does and doesn't prove:** all of this used `FakeExecutor` — scripted, in-memory responses, zero LLM involvement. It proves the scoring/aggregation/reporting *mechanics* are correct. It proves nothing about the AI's actual accuracy, because `RealPipelineExecutor` has never been run and no healthcare/PBM domain expert has authored a real scenario yet. The earlier blocker ("no Azure OpenAI credentials") no longer applies now that the LLM is self-hosted via Ollama with no account/credential needed — what's missing now is purely a real authored scenario, not infrastructure access.

**The path to real evidence:**
1. `docs/validation/real_call_procedure.md` — the exact runbook for the first real phone call, ready to execute (written against the earlier Azure-backed stack — needs a pass to confirm it still matches the self-hosted pipeline before relying on it verbatim).
2. `docs/validation/scenario_authoring_guide.md` + `app/evaluation/scenario_template.json` — the format for a domain expert to author real scenarios, with zero Python required.
3. `docs/validation/evidence_requirements.md` — for every capability claim (accuracy, grounding, PHI safety, tool correctness, escalation, resolution/containment, latency, reliability, cost, customer demand), exactly what evidence would need to exist before that claim is allowed to be made. Every row is honestly `UNKNOWN` today.
4. `docs/business/pilot_validation_plan.md` — ideal customer profile, pilot structure, and measurement plan for finding out whether a real organization will pay for this. No prospect has been contacted; this is preparation, not evidence of demand.
