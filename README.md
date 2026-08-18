# AI Workforce Platform

An AI voice customer-service platform for healthcare/PBM (pharmacy benefit manager) support. Callers talk to an AI agent over a real phone call; the AI answers from your uploaded documents, looks up real member/claim/pharmacy data, hands off between specialist agents, and everything is recorded, scored, and analyzable afterward.

This document covers: how it's built, what database it uses, how each feature works and where its data comes from/goes, what it costs to run, how to run it locally, and how to deploy it for a real phone number. For a pure checklist of accounts/keys/software, see [`SETUP.md`](SETUP.md).

---

## 1. Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.14, FastAPI, SQLAlchemy 2.0, Alembic (migrations) |
| Database | **PostgreSQL** with the **pgvector** extension (for semantic search) |
| Frontend | Angular 21 (standalone components, signals) |
| Voice | Twilio (phone number + real-time audio streaming over WebSocket) — a paid piece |
| LLM | **Anthropic Claude** (`claude-opus-5` by default) — conversational replies, call summaries, QA scoring, intent routing. A paid piece. |
| Speech-to-text | **Deepgram** (hosted, pre-recorded transcription API). A paid piece. |
| Text-to-speech | **Piper** — open source, runs locally, free |
| Embeddings | **Ollama**, self-hosted, free — `nomic-embed-text`, used only for the knowledge-base/RAG search |
| Auth | JWT (PyJWT), bcrypt password hashing, per-IP rate limiting on auth endpoints |

**Why three pieces of this aren't free.** This app started fully self-hosted (Ollama for everything, faster-whisper for STT) and moved the LLM and STT to hosted providers deliberately, for two concrete reasons hit during real testing:

1. **Compute capacity.** Self-hosted LLM/STT inference is bounded by whatever hardware runs it. On modest hardware, a capable enough model to follow "only answer from retrieved documents, never invent" reliably didn't fit in available RAM without becoming unusably slow — and even the model that did fit sometimes fabricated answers instead of using the correct document text. Hosted providers absorb that capacity problem; self-hosting it well means real GPU infrastructure most teams don't want to run themselves.
2. **Concurrency.** A single self-hosted model realistically serves a handful of concurrent conversations before quality or latency degrades. Handling many simultaneous calls needs either a GPU fleet with proper batching or a hosted API that scales elastically — the latter is the practical choice for most deployments (see [§6 Concurrency & scaling](#6-concurrency--scaling)).

Twilio remains unavoidable for a different reason: getting a real phone number that a caller can dial, and having that call reach your server, always goes through the public telephone network (PSTN) — there is no open-source way around that. Piper (TTS) and Ollama (embeddings only, not chat) stay self-hosted and free — neither one is the bottleneck the LLM/STT were.

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
        ├─ Deepgram transcribes the utterance
        ├─ (first utterance only) intent router may hand the call off to
        │   a specialist agent (Claims / Pharmacy / Benefits / ...)
        ├─ Claude gets the conversation + available tools, and either
        │   replies directly or calls a tool — e.g. verify_member,
        │   check_claim_status, search_documents, find_pharmacy
        ├─ tools query Postgres directly (Members/Claims/Drugs/Pharmacies/
        │   your uploaded documents' embedded chunks)
        ├─ every message and tool call is saved (conversation_messages,
        │   tool_execution_logs) — this is what the Conversations page shows
        └─ Piper speaks the reply back over the same WebSocket
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
Real-time Twilio audio ↔ Deepgram STT / Piper TTS ↔ Claude, with a multi-round tool-calling loop (the model can call several tools in sequence before replying) and barge-in support (below). This is the foundation everything else plugs into.

### Barge-in / interruption handling
While the AI's reply is playing, the handler keeps watching the caller's audio — not by transcribing continuously, but by checking every incoming frame's loudness. 200ms of sustained speech is treated as a genuine interruption (a click, cough, or brief noise isn't); on trigger, Twilio is told to clear the AI's queued audio immediately, and the caller's new utterance starts from the exact audio that triggered it, so they never have to repeat themselves. The loudness bar during AI playback is set higher than during normal turn-taking, specifically because a caller on speakerphone can have the AI's own voice leak back into their mic as echo — the higher bar makes that leaked echo less likely to falsely trigger a cutoff than genuine direct speech. Tunable via `BARGE_IN_MS`/`BARGE_IN_RMS_THRESHOLD` without a code change.

### Knowledge base / RAG
Upload PDFs or DOCX per agent (Agent Studio → an agent's page). Documents are parsed, split into chunks along paragraph boundaries (not a blind word-count window, which can cut a sentence in half), embedded (`nomic-embed-text` via Ollama, using the task-specific prefixes that model expects for indexed text vs. a search query), and stored in `knowledge_chunks` with a pgvector column. When the AI needs facts, it searches by cosine similarity against the caller's question.

### Confidence Engine
Every knowledge lookup gets a 0–100 score from how close the best-matching chunk is. **≥90% → answered normally. 70–89% → answered but hedged, source named. <70% → the source text is withheld entirely** — the model isn't just told to be careful, it literally never receives text it wasn't confident enough to trust. Scores are stored per-message (`conversation_messages.confidence_score`) and shown as a color-coded badge in the transcript. *(The 90/70 thresholds were tuned for an earlier embedding model; they haven't yet been re-validated against `nomic-embed-text`'s actual distance distribution — worth watching once real call volume exists.)*

### Citations
Every knowledge-grounded reply records which document/page it came from (`conversation_messages.citations`), shown as chips under the message in the transcript — visible to a supervisor, never read aloud on the call.

### Customer 360 Memory
Callers are recognized by phone number (`customer_profiles`). Returning callers get greeted by name, and the AI gets a short internal briefing on prior calls (intent + resolution only) — with a hard rule never to recite medical/claims specifics until identity is re-confirmed *in that call*.

### PBM / healthcare tools
`verify_member`, `check_claim_status`, `get_benefits`, `search_formulary`, `find_pharmacy`, `create_ticket`, `schedule_callback`, `send_email`, `update_customer`, plus `search_documents`, `schedule_appointment`, `escalate_to_human`. Claim/benefit lookups are hard-gated behind `verify_member` (member ID + DOB + ZIP) — no PHI is revealed pre-verification. Backed by real tables (`members`, `claims`, `drugs`, `pharmacies`); seed sample data with `backend/scripts/seed_pbm_data.py`. (`send_email` currently only records the intent to an audit log — no email provider is wired up yet; see [§8 Known gaps](#8-known-gaps-by-design-not-oversight).)

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

**Real capacity ceilings (infrastructure, not code):** actual concurrency is bounded by Claude's and Deepgram's rate limits for your account tier, Twilio's account-level concurrent-call limit (raised via a support request, not code), a single `uvicorn` process being one Python event loop, and Postgres's own `max_connections`. None of this is provable from code review — it needs real load testing against your actual provider rate limits before you can honestly claim a specific concurrent-call number. For real scale, the app tier itself can scale horizontally (multiple stateless backend instances behind a WebSocket-capable load balancer) — that part is a legitimate, doable engineering project; the LLM/STT/telephony capacity is a matter of your account limits and budget with those providers.

---

## 7. Cost

Three real per-usage costs, plus one that's free:

| Component | Basis | Approx. cost |
|---|---|---|
| **Claude (LLM)** | Token-based — grows with call length and tool/RAG use | ~$0.03/min (rough estimate, see caveat below) |
| **Deepgram (STT)** | Per-minute, Nova-2 pay-as-you-go rate | ~$0.004/min |
| **Twilio** | Phone number rental + inbound voice + Media Streams | ~$1–2/month + ~$0.0125/min |
| **Piper (TTS) + Ollama (embeddings)** | Self-hosted | $0 |

**~$0.05/minute all-in** is a reasonable planning estimate for a typical call — but it's an estimate with real assumptions (see the LLM row), not a bill. Longer or tool-heavy calls (document lookups inject retrieved text into the conversation) cost more per minute, not less, since the LLM resends the whole conversation history each turn and no prompt caching is wired up yet. Check your actual Anthropic/Deepgram dashboards after real call volume rather than trusting this number long-term.

**Compared to a human CSR:** this app's own dashboard already assumes $12/human-handled call (`ASSUMED_COST_PER_HUMAN_CALL` in `dashboard.py`, explicitly labeled there as a stated assumption, not measured accounting). At a ~5-minute average handle time that's roughly $2.40/minute for a human agent vs. ~$0.05/minute for the AI — **roughly 40–50x cheaper per minute of talk time.** The honest framing isn't "AI replaces humans" — it's "AI absorbs the high-volume, well-defined majority of calls at a fraction of the per-minute cost, and hands the genuinely hard ones to `escalate_to_human`," which is exactly how the confidence thresholds and escalation tool are architected, not an accident.

---

## 8. Running it locally

**Prerequisites**: Python 3.14, Node.js + npm, PostgreSQL with the `pgvector` extension available, [Ollama](https://ollama.com) installed and running (embeddings only), an Anthropic API key, a Deepgram API key, a Twilio account (for real calls — not required just to browse the dashboard). See [`SETUP.md`](SETUP.md) for the full account/key checklist.

### Install Ollama and pull the embedding model

```bash
# https://ollama.com/download
ollama pull nomic-embed-text    # embedding model — chat no longer runs through Ollama
ollama serve                    # runs on http://localhost:11434 (often already running as a service)
```

### Download Piper voice models

```bash
cd backend
mkdir voices && cd voices
python -m piper.download_voices en_US-amy-medium
python -m piper.download_voices en_US-ryan-medium
python -m piper.download_voices en_GB-alan-medium
python -m piper.download_voices hi_IN-rohan-medium
cd ..
```
(Only `PIPER_DEFAULT_VOICE` is required to get calls working; download the rest only if you'll assign them to agents in Agent Studio.)

**If a voice fails to load with `onnxruntime...INVALID_PROTOBUF: ...Protobuf parsing failed`**: the `.onnx` file downloaded incomplete/corrupted — `piper.download_voices` doesn't verify download integrity, so this happens on a flaky connection. Delete the two files for that voice from your voices directory and re-run the download command (or retry a couple of times); a good download of a "medium" voice is ~60MB.

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
ANTHROPIC_API_KEY=<from console.anthropic.com>
ANTHROPIC_MODEL=claude-opus-5
DEEPGRAM_API_KEY=<from console.deepgram.com>
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIM=768
PIPER_VOICES_DIR=./voices
PIPER_DEFAULT_VOICE=en_US-amy-medium
TWILIO_ACCOUNT_SID=...
TWILIO_AUTH_TOKEN=...
PUBLIC_SERVER_URL=...           # see deployment section — must be a real public HTTPS URL to take real calls
CORS_ORIGINS=http://localhost:4200
```

Run migrations, then start the API:

```bash
alembic upgrade head
uvicorn app.main:app --port 8001 --reload
```

(Optional) seed sample PBM data so the healthcare tools have something to look up:

```bash
python scripts/seed_pbm_data.py <your-tenant-slug>
```

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
2. **Agent Studio** — create an AI agent: name, voice, persona, department (leave as "general" unless you're setting up multi-agent routing). Upload PDFs/DOCX to give it a knowledge base.
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
- **No billing/monetization layer** — no Stripe or usage-based plan enforcement for your own customers; Twilio/Claude/Deepgram costs are what a tenant's calls cost *you*, with no built-in way to charge them for it.
- **No platform admin console** — onboarding a tenant's Twilio number needs a raw SQL update (Step 3 above), not a UI.
- **Real concurrent-call capacity is unverified** — the code-level thread/connection-pool ceilings are fixed, but actual throughput depends on your Claude/Deepgram/Twilio account limits and hasn't been load-tested (see [§6](#6-concurrency--scaling)).
- **Confidence thresholds (90/70) aren't re-validated** for the current embedding model — see [§4 Confidence Engine](#confidence-engine).
