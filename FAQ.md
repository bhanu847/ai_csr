# FAQ

Answers to the questions asked while building this out. For full system docs (architecture, every feature, deployment steps, database details), see [README.md](README.md) — this file is the shorter Q&A version.

---

## 1. How many seconds does the agent take to reply — and where does the answer actually come from?

### Timing

Every turn runs through five steps **in sequence, not streaming** — each one waits for a full result before the next starts:

| Step | What happens | Measured (this project's CPU-only dev machine — Intel UHD 620 iGPU, no discrete GPU) |
|---|---|---|
| Silence detection | The system waits 700ms of silence after you stop talking before it even starts processing (`SILENCE_DURATION_MS = 700` in `vad.py`) | 0.7s fixed |
| Speech-to-text | Your whole utterance transcribed locally by faster-whisper (`base` model) | ~1.5s warm (measured) |
| LLM thinks | Ollama (local, `qwen3:1.7b` by default, thinking disabled — see below) generates the complete reply before returning anything | ~15–19s warm (measured). `qwen3:8b`, the heavier alternative, measured **~140–150s per call on this hardware** — unusable live; only consider it with a GPU, which hasn't been measured here. |
| *(if a tool is used, e.g. a claim lookup)* | DB lookups are fast (~10–100ms), but a knowledge search adds a local embedding call, and using a tool means a **second** full LLM round-trip for the final reply | roughly another LLM-step's worth of time |
| Text-to-speech | Full audio synthesized locally by Piper before anything is sent back | ~400–470ms warm (measured) |

**On this machine:** a simple reply is in the ~17–22 second range end-to-end, dominated almost entirely by the LLM step — a tool-using reply roughly doubles that. These are real measurements, not estimates, and they're specific to CPU-only inference on modest laptop hardware with no GPU; a GPU (for Ollama especially) would change this substantially, but that hasn't been tried. This is the direct tradeoff of the self-hosted swap (see [README.md § 1](README.md#1-tech-stack)): $0 per call, but slower than hosted GPU-backed inference unless you provide your own GPU.

Nothing is streaming today (not STT, not the LLM, not TTS) — that's the single biggest lever to cut perceived latency if it ever needs to feel snappier.

### Where the content comes from

Three different sources, and the AI is instructed never to blend them:

1. **Your uploaded PDF/DOCX** — for factual questions, via `search_documents` doing a pgvector similarity search over the knowledge base. If nothing relevant was uploaded, there's **no fallback to general AI knowledge** — the system prompt forbids inventing policies/prices/dates, so it says it doesn't know instead.
2. **Your live database** — for account-specific questions (claim status, pharmacy lookup), via PBM tools querying `members`/`claims`/`drugs`/`pharmacies` directly. **Never PDF content.**
3. **The model's own conversation** — greetings, clarifying questions, asking for your member ID — not grounded in any document or lookup, just the persona talking.

---

## 2. How do I connect a PDF or live data to the application?

**PDFs** — already fully working: Agent Studio → open an agent → drag a PDF/DOCX onto the Knowledge base panel. It's parsed, chunked, embedded, and searchable immediately. Knowledge is scoped **per agent** — a Pharmacy agent only sees what's been uploaded to it, not what's on the Claims agent.

**Live data (your real members/claims/formulary/pharmacies)** — there's no external system connector. Two ways to load it:
- `backend/scripts/seed_pbm_data.py` — sample/test data only.
- **Data Import page** (sidebar → Data Import) — upload a CSV export, map its columns to our fields (your export doesn't need to match our column names), preview, and import. Re-uploading an updated export **updates existing records instead of duplicating them** (matched by Member ID / Claim Number / Drug name / Pharmacy name+ZIP). One bad row in the CSV doesn't block the rest — you get a per-row error back.
  - Dates must be `YYYY-MM-DD` in the CSV today — no auto-detection of other date formats yet.
  - Claims reference Members by Member ID, so import Members first.

If your real data instead lives behind an API (a real PBM/claims system), that's a different build (a live integration adapter) — say so if that's actually your situation and I'll build that path instead.

---

## 3. What does each feature do, how does data flow, and will it work immediately on a live call?

Full per-feature breakdown and a data-flow table are in [README.md § 4](README.md#4-features) and [§ 3](README.md#3-how-a-phone-call-actually-works-the-core-loop). Short version of the live-call question, using "why is my claim pending" as the example:

- **It won't answer on the first sentence.** Claim/benefit lookups are gated behind identity verification (member ID + DOB + ZIP) — deliberately, so no PHI is revealed before the caller proves who they are. The real exchange is: caller asks → AI asks for verification → caller answers → AI verifies → *then* looks up the claim and answers.
- **Adding API keys alone does not connect your phone number.** Twilio needs a **publicly reachable HTTPS URL** for its webhook (`localhost` doesn't work — you need a tunnel like ngrok for testing, or a real deployment), the Twilio console needs the webhook URLs configured, and your number needs to be registered in the `tenants` table. Full steps: [README.md § 6](README.md#6-deploying-for-real-phone-calls).
- Once that's in place, calling the number does ring through to a real, working AI agent — that part isn't a mockup.

---

## 4. How do I deploy this, what database does it use, and how do I use it day to day?

Fully covered in [README.md](README.md):
- **Database**: PostgreSQL + the `pgvector` extension — required, not optional (semantic search and multi-tenant Row-Level Security both depend on it). Table list: [README.md § 2](README.md#2-database).
- **Local dev setup**: [README.md § 5](README.md#5-running-it-locally).
- **Deployment checklist** (public URL, Twilio webhook config, registering your number, hosting frontend/backend/Postgres): [README.md § 6](README.md#6-deploying-for-real-phone-calls).
- **Day-to-day usage walkthrough** (Agent Studio → knowledge → workflows → going live → watching it work in Live Operations/Conversations/Analytics): [README.md § 7](README.md#7-using-the-application).
- **Known gaps**, stated plainly rather than glossed over: [README.md § 8](README.md#8-known-gaps-by-design-not-oversight).
