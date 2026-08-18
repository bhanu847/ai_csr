# Real-Call Validation Procedure

**Purpose:** the exact, unambiguous sequence to run the moment Azure credentials exist, so there is zero delay or improvisation between "credentials arrive" and "first real call measured." This document is the procedure; it contains no results, because no real call has happened yet.

**Status of everything in this document: NOT YET EXECUTED.** Every step below is prepared, not performed.

---

## Pre-flight checklist (before dialing anything)

- [ ] `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` set in `backend/.env`
- [ ] Backend restarted so it picks up the new env vars
- [ ] `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` set; a real Twilio number purchased and Voice-capable
- [ ] `PUBLIC_SERVER_URL` set to a real reachable HTTPS URL (ngrok for a first test is fine) and the Twilio number's webhooks point at it (see `README.md` §9)
- [ ] `tenants.twilio_phone_number` set for the test tenant
- [ ] At least one agent exists, is set as the tenant's default agent, has a real Azure voice name (e.g. `en-US-JennyNeural`) in its `voice` field
- [ ] Someone is ready to actually place the call and someone (can be the same person) is watching backend logs live

## Step 0 — Isolate each Azure service before routing a real call through all of them

Do this before Step 1. If a component is broken, better to find out here than mid-call.

1. **Azure OpenAI in isolation** — one direct chat-completion request (curl or a short script) against the configured deployment. Confirms: API key valid, endpoint reachable, deployment name correct, gets a real completion back.
2. **Azure Speech STT in isolation** — send one short pre-recorded WAV through `app.speech.stt.transcribe_pcm16` directly (not through a call) and confirm the transcript is correct.
3. **Azure Speech TTS in isolation** — call `app.speech.tts.synthesize_mulaw8k` directly with a short string, save the returned bytes as mu-law audio, and listen to it (or convert to WAV for playback) to confirm real audio comes back and the voice sounds right.

**Record for each:** did it work (yes/no), latency of the single call, any error message verbatim.

**Gate:** do not proceed to Step 1 until all three pass individually. A failure here is faster and cheaper to diagnose than a failed real call.

## Step 1 — The first real phone call (minimal scenario)

Call the Twilio number from a real phone. Say only:
1. Wait for the greeting.
2. Say a simple, unambiguous, non-PBM question (e.g. "what are your hours" if a knowledge document with that answer is loaded, or literally "hello, can you hear me").
3. Hang up.

**This call is not trying to prove the product works.** It is trying to prove the five services (Twilio → Azure STT → Azure OpenAI → Azure TTS → Twilio) can complete one round trip without crashing.

**Immediately after the call, capture:**
- Did the caller hear a greeting at all? (yes/no)
- Did the AI respond to the question at all, coherently? (yes/no)
- Backend logs: any exception/traceback during the call? (paste verbatim if yes)
- `calls` table: does a row exist with `status = completed`?
- `conversation_messages` table: does the transcript look right?

**Gate:** if this fails, stop and fix before Step 2. Do not add complexity to a broken foundation.

## Step 2 — Add one dimension of complexity at a time

Once Step 1 succeeds, run one additional short call for each of the following, **one at a time**, not combined:

| Call # | What to test | What "success" means |
|---|---|---|
| 2 | A question that requires a tool call (e.g. `search_documents` against an uploaded doc) | Correct tool called (check `tool_execution_logs`), correct info in the reply |
| 3 | `verify_member` with correct seeded credentials, then a claim question | Verification succeeds, claim info correct, matches seeded DB |
| 4 | A claim/benefit question with NO prior verification | Reply correctly declines and asks to verify — no PHI disclosed |
| 5 | Interrupt the AI mid-reply (talk over it) | Barge-in triggers: AI audio stops, new utterance captured |
| 6 | A question the knowledge base has no good answer for | AI declines / escalates rather than inventing an answer |

For each call, capture the same measurement set as Step 1, plus the specific pass/fail for that call's purpose.

## Measurements to capture for every call (Steps 1–6)

Record these in a simple table (spreadsheet or the JSON evaluation report format from `app/evaluation/`) — do not just remember them:

**Latency** (from backend logs / manual stopwatch until real instrumentation exists — see "Known gap" below):
- Time from caller finishing speaking to AI starting to respond (the number that matters most to a caller)
- STT time (if loggable), LLM time, TTS time, broken out if possible

**Correctness** (manual judgment by whoever is listening):
- Transcription accuracy — did Azure STT get the words right? Note any misheard words.
- Response correctness — was the AI's answer actually right?
- Tool correctness — right tool, right arguments (check `tool_execution_logs.input`)
- Voice quality — does it sound natural, are there audio glitches, was the reply audio complete or cut off unexpectedly

**Reliability:**
- Any exception in backend logs, even a caught/recovered one
- Any Twilio-side error (check the Twilio console's call log/debugger for that call)

**Cost:**
- Azure OpenAI: token usage for this call (Azure Portal → your OpenAI resource → Metrics, or via the deployment's usage log — **not currently surfaced in-app**, see Known gap below)
- Azure Speech: minutes used (Azure Portal → Speech resource → Metrics)
- Twilio: cost for this call (Twilio Console → this call's detail page)

## Known gap this procedure exposes

`app/llm/client.py` does not currently capture or return token usage, so per-call LLM cost cannot be read from the app itself yet — it has to be pulled from the Azure Portal manually per call during this phase. If real-call volume moves past manual spreadsheet tracking, capturing `response.usage` from the Azure OpenAI response and threading it into `ObservedBehavior.cost_usd` (see `app/evaluation/schema.py`) is the concrete next engineering step — not before there's a reason to need it.

## Decision gate before scaling to 10 calls

Do not proceed to controlled batches of 10/100/500 calls (see the real-validation plan) until:
- Steps 1–6 above have all been run at least once
- Every failure has been triaged: bug fixed, or logged as a known limitation, or evidence the workflow shouldn't be automated as-is
- There is no unexplained crash or silent failure in the batch

If Steps 1–6 reveal the pipeline is fundamentally unreliable, that is a valid and useful outcome of this procedure — it means fixing the pipeline is the next step, not running more calls through it.
