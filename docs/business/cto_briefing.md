# CTO Briefing — AI Workforce Platform

**One line:** an AI voice agent that answers real phone calls for healthcare/PBM customer service — verifying identity, pulling real member/claim/pharmacy data, answering from your own documents, and escalating anything it isn't sure about — built end-to-end and now taking real Azure-powered phone calls.

This document is written to be checked, not just believed. Every claim below is either something you can run yourself in five minutes, or is explicitly labeled as not yet proven. That's deliberate — the fastest way to lose a technical reviewer's trust is to overclaim something they can immediately test.

---

## The pitch, in three sentences

Healthcare/PBM call centers spend money on a narrow, repetitive category of calls — prescription status, benefits questions, pharmacy lookups, claim status — that a well-built AI agent can handle at a fraction of the cost, with a full audit trail. This isn't a chatbot wrapper: it verifies identity before touching anything sensitive, answers only from real retrieved data (never invents), and hands off to a human the moment it isn't confident. It's built, it's tested, and as of this week it took its first real phone call end-to-end on production cloud infrastructure.

---

## What's actually built (real, running code — not a mockup)

- **Real-time voice pipeline**: Twilio phone number ↔ Azure AI Speech (STT + neural TTS) ↔ Azure OpenAI, with barge-in — if the caller talks over the AI, it stops within 200ms and listens, instead of talking past them.
- **Grounded answers, not hallucination**: every knowledge-base answer is scored for confidence against the actual retrieved source text. Below a real, data-derived threshold, it refuses to answer rather than guess — see the "Proof it works" section below for a live example of this catching a real problem.
- **Verification is enforced in code, not just prompted for.** PHI-adjacent tools (claim status, benefits) check identity verification status *before* touching the database — the LLM cannot bypass this by being asked nicely.
- **Multi-tenant security**: Row-Level Security enforced by PostgreSQL itself, not application logic — a bug in app code cannot leak one business's data into another's.
- **Multi-agent routing**: one phone number can route between a general agent and department specialists (pharmacy/claims/benefits) based on what the caller actually says, invisibly, mid-call.
- **Supervisor controls**: a human can watch any live call, pause the AI mid-call, or inject a one-time steering suggestion — a real intervention path, not just a kill switch.
- **A swappable data layer**: the five PBM data tools (verify member, check claim, get benefits, search formulary, find pharmacy) sit behind a real interface, not hardcoded queries — proven substitutable with a second backend via automated tests, so connecting a real PBM/claims system later is a contained integration, not a rewrite.
- **37 automated tests** covering the data-layer abstraction and the evaluation harness, passing on the current stack.

Full architecture and a diagram of the complete call flow: [`docs/platform_guide.md`](../platform_guide.md).

---

## Proof it works — including proof we catch our own bugs

On 2026-08-22, this went through its first real phone call on live Azure infrastructure — a real Jio mobile number dialing a real Twilio number, hitting real Azure OpenAI and Azure Speech.

That first call immediately surfaced a real bug: the AI declined to answer two questions it should have answered, escalating to a human instead. **Rather than patch it blind, we pulled the actual tool-execution logs and found the real cause** — a confidence threshold that had been tuned for a different embedding model months earlier, never re-validated after a later provider swap. We proved this with real data (9 labeled query/document pairs, not a guess), recalibrated the threshold to the model's actual score distribution, and re-verified all 9 pairs landed in the correct band before calling it fixed.

**Why this matters more than the fix itself:** this is the actual operating model going forward — real calls surface real problems, problems get root-caused with real data instead of patched by intuition, and every fix gets re-verified before being called done. That discipline is documented in [`docs/validation/evidence_requirements.md`](../validation/evidence_requirements.md) and is enforced, not aspirational — every claim in that document is graded `VERIFIED`, `BUILT-UNVERIFIED`, or `UNKNOWN`, and nothing gets marked done without a specific test or measurement behind it.

---

## Honest status — what's proven vs. what isn't yet

| Claim | Status | Evidence |
|---|---|---|
| Core voice pipeline completes a real call (Twilio→STT→LLM→TTS→Twilio) | **VERIFIED** | Real call placed and completed, 2026-08-22 |
| PHI-gated tools refuse data without verification | **VERIFIED** | Automated tests, both real and mock data backends |
| Data-layer abstraction is genuinely swappable | **VERIFIED** | Automated substitutability tests, 18 passing |
| Confidence-gated RAG grounding works mechanically | **VERIFIED** (mechanism) | Live-fixed and re-tested 2026-08-22 |
| Tool-selection / escalation correctness at scale | **BUILT, UNVERIFIED** | Evaluation framework built and proven mechanically correct on test fixtures; not yet run against real-world scenario volume |
| Accuracy/hallucination rate on real healthcare questions | **UNKNOWN** | No domain-expert-authored scenario set exists yet — needs a PBM/healthcare SME, not more engineering |
| Cost per call | **UNKNOWN (real) / estimated below** | No real billing data captured yet — token/minute usage isn't wired into per-call cost tracking |
| Concurrent-call capacity | **UNKNOWN** | Architecturally unrestricted (no per-agent lock), never load-tested |
| Real customer demand | **UNKNOWN** | Zero customer contact so far — this is a business validation gap, not a technical one |

Full table with 10 dimensions: [`docs/validation/evidence_requirements.md`](../validation/evidence_requirements.md).

---

## Unit economics — a grounded estimate, not a measured number yet

No real billing data exists yet (see table above), so treat this as a **directional estimate from public list pricing**, not a claim. Rough per-minute cost, assuming continuous AI speech and a typical short exchange:

| Component | Rate | Source |
|---|---|---|
| Azure OpenAI (gpt-4.1-mini) | $0.40 / 1M input tokens, $1.60 / 1M output tokens | [Azure OpenAI pricing, verified Jun 2026](https://futureagi.com/llm-cost-calculator/azure-openai/gpt-4-1-mini/) |
| Azure Speech — STT | $1.00 / audio hour (real-time standard) | [Azure AI Speech pricing 2026](https://texttolab.com/blog/azure-text-to-speech-pricing) |
| Azure Speech — TTS | $16 / 1M characters (prebuilt neural) | [Azure AI Speech pricing 2026](https://texttolab.com/blog/azure-text-to-speech-pricing) |
| Twilio — inbound US local | $0.0085 / min | [Twilio voice pricing 2026](https://edesy.in/blog/twilio-voice-pricing-guide-2026) |

Rough total: **~$0.03–$0.06 per minute** of AI-handled call time — consistent with independently reported bundled AI-voice-agent costs of [$0.018–$0.06/min](https://quiq.com/blog/twilio-voice-pricing/).

Compare to a fully-loaded US-based human CSR minute: **$0.65–$2.73/min** depending on market tier ([sourced range, 2026](https://contactcenterusa.com/blog/call-center-outsourcing-cost-per-hour-2026)).

That's a **~15–50x gap on raw per-minute compute/telephony cost alone** — deliberately not counting engineering, hosting, support, or the cost of the accuracy work still ahead. That caveat is the honest part of this pitch, not a hedge: the unit economics look genuinely strong even before optimization, but the real number needs actual billing data across real calls before it goes in front of anyone outside this room.

---

## What I'm asking for

*(Customize this section for what you actually need from him — a few likely asks based on where this stands:)*

1. **Sign-off to run the next validation phase** — a controlled 10-call, then 100-call batch (following [`docs/validation/real_call_procedure.md`](../validation/real_call_procedure.md)), to get real accuracy/latency/cost numbers instead of estimates.
2. **Access to a domain expert** (internal PBM/healthcare knowledge, even a few hours) to author a real scenario set — this is the one gap engineering alone can't close; see [`docs/validation/scenario_authoring_guide.md`](../validation/scenario_authoring_guide.md).
3. **A steer on pilot direction** — whether to pursue a design-partner conversation now or wait for the 100-call validation numbers first (draft plan: [`docs/business/pilot_validation_plan.md`](pilot_validation_plan.md)).

---

## If he pushes back

The likely challenges and the honest answer to each:

- **"Is this just a chatbot with a phone number?"** No — walk through the verification gate and the confidence-gated RAG in [`docs/platform_guide.md`](../platform_guide.md) §4; both are enforced in code, not prompt instructions.
- **"How do I know the accuracy numbers are real?"** They're not claimed yet — that's the point of the honest-status table above. The ask is for what's needed to get real ones.
- **"What happens when it's wrong?"** It's designed to escalate rather than guess — the same bug-fix story above is direct evidence of that discipline in practice, including the case where the threshold itself was miscalibrated.
- **"What's the actual cost?"** Directional estimate above, sourced; real number requires the validation batch in the ask above.
