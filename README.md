# AI Workforce Platform

An AI voice customer-service platform for healthcare/PBM (pharmacy benefit manager) support. Callers talk to an AI agent over a real phone call; the AI answers from your uploaded documents, looks up real member/claim/pharmacy data, hands off between specialist agents, and everything is recorded, scored, and analyzable afterward.

This document covers: how it's built, what database it uses, how each feature works and where its data comes from/goes, how to run it locally, and how to deploy it for a real phone number.

---

## 1. Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.14, FastAPI, SQLAlchemy 2.0, Alembic (migrations) |
| Database | **PostgreSQL** with the **pgvector** extension (for semantic search) |
| Frontend | Angular 21 (standalone components, signals) |
| Voice | Twilio (phone number + real-time audio streaming over WebSocket) |
| Speech | Azure Cognitive Services Speech (speech-to-text and text-to-speech) |
| AI | Azure OpenAI (chat completions + text embeddings) |
| Auth | JWT (PyJWT), bcrypt password hashing |

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

Every table except `tenants` (which has no tenant context yet — it's how a tenant gets resolved in the first place) and the append-only log tables enforces RLS. Migration history lives in `backend/alembic/versions/` — 11 migrations, applied in order, each one additive (nothing in this project has ever rewritten or dropped existing data).

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
        └─ speaks a greeting (Azure TTS) — by name, if the caller is known
        │
Caller speaks (repeats every turn)
        ├─ voice activity detection buffers audio until the caller pauses
        ├─ Azure Speech-to-Text transcribes it
        ├─ (first utterance only) intent router may hand the call off to
        │   a specialist agent (Claims / Pharmacy / Benefits / ...)
        ├─ the LLM (Azure OpenAI) gets the conversation + available tools,
        │   and either replies directly or calls a tool — e.g. verify_member,
        │   check_claim_status, search_documents, find_pharmacy
        ├─ tools query Postgres directly (Members/Claims/Drugs/Pharmacies/
        │   your uploaded documents' embedded chunks)
        ├─ every message and tool call is saved (conversation_messages,
        │   tool_execution_logs) — this is what the Conversations page shows
        └─ Azure Text-to-Speech speaks the reply back over the same WebSocket
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
Real-time Twilio audio ↔ Azure STT/TTS ↔ Azure OpenAI, with a multi-round tool-calling loop (the model can call several tools in sequence before replying). This is the foundation everything else plugs into.

### Knowledge base / RAG
Upload PDFs or DOCX per agent (Agent Studio → an agent's page). Documents are parsed, split into chunks, embedded (Azure OpenAI embeddings), and stored in `knowledge_chunks` with a pgvector column. When the AI needs facts, it searches by cosine similarity against the caller's question.

### Confidence Engine
Every knowledge lookup gets a 0–100 score from how close the best-matching chunk is. **≥90% → answered normally. 70–89% → answered but hedged, source named. <70% → the source text is withheld entirely** — the model isn't just told to be careful, it literally never receives text it wasn't confident enough to trust. Scores are stored per-message (`conversation_messages.confidence_score`) and shown as a color-coded badge in the transcript.

### Citations
Every knowledge-grounded reply records which document/page it came from (`conversation_messages.citations`), shown as chips under the message in the transcript — visible to a supervisor, never read aloud on the call.

### Customer 360 Memory
Callers are recognized by phone number (`customer_profiles`). Returning callers get greeted by name, and the AI gets a short internal briefing on prior calls (intent + resolution only) — with a hard rule never to recite medical/claims specifics until identity is re-confirmed *in that call*.

### PBM / healthcare tools
`verify_member`, `check_claim_status`, `get_benefits`, `search_formulary`, `find_pharmacy`, `create_ticket`, `schedule_callback`, `send_email`, `update_customer`, plus `search_documents`, `schedule_appointment`, `escalate_to_human`. Claim/benefit lookups are hard-gated behind `verify_member` (member ID + DOB + ZIP) — no PHI is revealed pre-verification. Backed by real tables (`members`, `claims`, `drugs`, `pharmacies`); seed sample data with `backend/scripts/seed_pbm_data.py`.

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
Dashboard: active calls, resolution rate, estimated cost saved (explicitly labeled as an *estimate*, not accounting), recent conversations. Analytics: top intents, sentiment mix, resolution trend over time — all computed live from `calls`, nothing precomputed or faked.

### AI Training Center
On demand ("Run analysis" button), scans recent low-confidence answers, escalations, and low-QA calls for **recurring patterns** (not one-offs) and suggests: upload this document / adjust this behavior / fix this process gap. Insights are saved so a supervisor can acknowledge or dismiss them.

### Live Operations (Supervisor Command Center)
Live list of in-progress calls (polls every 4s), each call's most recent turn and confidence. A supervisor can:
- **Monitor** — open the live transcript (same drawer as Conversations, refreshes as new turns come in)
- **Stop AI** — the AI immediately stops generating replies and gives a holding line instead, until resumed
- **Send suggestion** — a note that gets folded into the AI's *next* reply only, then discarded

**Not implemented: Join call / Transfer call.** Both need real Twilio conference/audio-bridging, which needs a live phone call to test against — I didn't ship code I couldn't verify actually works.

---

## 5. Running it locally

**Prerequisites**: Python 3.14, Node.js + npm, PostgreSQL with the `pgvector` extension available, an Azure OpenAI resource, an Azure Speech resource, a Twilio account (for real calls — not required just to browse the dashboard).

### Backend

```bash
cd backend
python -m venv venv
venv/Scripts/activate          # venv\Scripts\activate.bat on plain cmd
pip install -r requirements.txt
```

Create `backend/.env` (see `backend/.env.example` for the full template):

```
DATABASE_URL=postgresql+psycopg://app_user:CHANGE_ME@localhost:5432/ai_workforce
MIGRATIONS_DATABASE_URL=postgresql+psycopg://postgres:CHANGE_ME@localhost:5432/ai_workforce
JWT_SECRET=<long random string>
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_DEPLOYMENT=...
AZURE_OPENAI_EMBEDDING_DEPLOYMENT=...
AZURE_SPEECH_KEY=...
AZURE_SPEECH_REGION=...
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

## 6. Deploying for real phone calls

This is the part that trips people up: **adding API keys alone does not connect a phone number.** Three things have to line up.

### Step 1 — Host the backend somewhere with a public HTTPS URL
`localhost` is not reachable by Twilio's servers. Options:
- **Quick test**: `ngrok http 8001` while running locally — gives you a temporary public HTTPS URL.
- **Real deployment**: any host that can run the FastAPI app behind HTTPS (a VM, a container platform, etc.) with a real domain.

Whatever URL you end up with, set it as `PUBLIC_SERVER_URL` in `backend/.env`. It's used two ways: as the Twilio webhook base, and (converted to `wss://`) as the live audio WebSocket URL.

### Step 2 — Configure the Twilio number
In the Twilio console, on the phone number you want to use:
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

## 7. Using the application

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
   - **Dashboard / Analytics** — aggregate trends.
   - **AI Training Center** — click "Run analysis" periodically to surface patterns worth fixing (missing docs, prompt issues).

---

## 8. Known gaps (by design, not oversight)

- **No live audio join/transfer** for supervisors (Live Operations) — needs real Twilio conference work, untested here.
- **No drag-and-drop workflow canvas** — workflows are an ordered step list, functionally equivalent, not visually a node graph.
- **No admin UI yet** for registering a tenant's Twilio number — direct DB access required.
- **Frontend API URLs are hardcoded** to `localhost:8001` — needs an environment-based config swap before a real multi-environment deployment.
- **"Cost saved" on the dashboard is a stated estimate** (`resolved calls × assumed cost/call`), not real accounting.
- **Claim `PENDING` status has no stored reason** — only rejected claims have a `rejection_reason`; the AI can say a claim is pending but not yet explain *why*.
