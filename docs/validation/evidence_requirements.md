# Evidence Requirements — What We Need Before Claiming This Works

**Purpose:** one place that defines, for every capability this product claims to have, exactly what evidence would need to exist before that claim is allowed to be made — to someone internal, in a pitch, or in a README. Where evidence doesn't exist yet, this document says so as `UNKNOWN`, not as "should be fine."

**Rule this document exists to enforce:** a capability's status can only change when a new row is added to its Evidence column with a specific, checkable artifact (a test, a measurement, a report) — never by narrative confidence.

---

## How to read this table

- **Claim** — the thing someone might want to say about the product.
- **What would prove it** — the specific measurement or test, including minimum sample size where sample size matters.
- **Current evidence** — what exists today. `NONE` if nothing does.
- **Status** — `VERIFIED` / `BUILT-UNVERIFIED` / `NOT IMPLEMENTED` / `UNKNOWN`, per the project's standing taxonomy.

## Accuracy

| Claim | What would prove it | Current evidence | Status |
|---|---|---|---|
| The AI answers healthcare/PBM questions correctly | Expert-reviewed scenario set (not the harness fixtures — see `scenario_authoring_guide.md`) run through `RealPipelineExecutor`, scored on `answer_content`, at a sample size large enough to bound a confidence interval on the pass rate (rule of thumb: at least ~100 scenarios per category before quoting a percentage; more for a number going in front of a customer) | NONE — no expert scenarios exist, and `RealPipelineExecutor` has never run (Azure blocked) | UNKNOWN |
| Hallucination rate is low | Same scenario set, specifically scoring cases where the correct behavior is "decline / escalate" vs. the AI inventing an answer | NONE | UNKNOWN |

## Grounding

| Claim | What would prove it | Current evidence | Status |
|---|---|---|---|
| RAG answers only use retrieved document text | Direct retrieval test comparing on-topic vs. off-topic query similarity scores | One manual test session, one document, three queries (see project history) | BUILT-UNVERIFIED — real but far too small a sample to claim general grounding behavior |
| The 90/70 confidence thresholds correspond to actual correctness rates | Calibration study: for a labeled set of (query, correct-or-not) pairs, plot confidence score vs. actual correctness and check the 90/70 cut points are meaningful | NONE | NOT IMPLEMENTED |

## Verification / PHI safety

| Claim | What would prove it | Current evidence | Status |
|---|---|---|---|
| PHI-gated tools refuse to return data without verification | Automated test: call `check_claim_status`/`get_benefits` with no verification, assert the gate fires, for every `PBMProvider` implementation | `tests/pbm/test_substitutability.py` — 2 tests, passing, run against both Postgres and Mock providers | VERIFIED (for the mechanism itself, at the code level) |
| The AI never discloses PHI in a live call when it shouldn't | Real/scenario calls specifically probing this (a caller asking for someone else's info, a caller who fails verification then tries again with a different approach), scored on `answer_must_not_contain` for PHI markers, **target: zero occurrences across the full scenario/call set, not a percentage** | NONE — no real or expert scenario has tested this | UNKNOWN |

## Tool correctness

| Claim | What would prove it | Current evidence | Status |
|---|---|---|---|
| The AI calls the right tool with the right arguments | `tool_selection` dimension in the evaluation framework, run against real scenarios at volume | Framework built and proven mechanically correct on 5 harness fixtures (not real scenarios) | BUILT-UNVERIFIED |

## Escalation

| Claim | What would prove it | Current evidence | Status |
|---|---|---|---|
| The AI escalates when it should (frustrated caller, out-of-scope request, low confidence) | `escalation` dimension scored against real/expert scenarios covering these cases | Framework proven on 1 harness fixture | BUILT-UNVERIFIED |
| The AI does NOT escalate unnecessarily (false escalation) | Same scenario set, scored for cases where the AI should resolve directly but escalates instead | NONE | UNKNOWN |

## Resolution / containment

| Claim | What would prove it | Current evidence | Status |
|---|---|---|---|
| X% of calls are resolved without human intervention | Real call batches (10 → 100 → 500, per the real-call procedure), counting resolved vs. escalated vs. abandoned vs. incorrectly handled | NONE — zero real calls placed | UNKNOWN |

## Latency

| Claim | What would prove it | Current evidence | Status |
|---|---|---|---|
| Response time is acceptable for a live phone call | Per-call latency measurement (caller-stops-talking to AI-starts-responding), captured per `real_call_procedure.md` | NONE against real Azure. A same-session-only latency comparison exists for a *different* stack (local Ollama, thinking-mode on/off) — not representative of the current Azure path | UNKNOWN |

## Reliability

| Claim | What would prove it | Current evidence | Status |
|---|---|---|---|
| The pipeline doesn't crash or fail silently under real conditions | Real call batches with 100% of failures triaged (bug / known limitation / shouldn't-be-automated), technical-failure rate tracked | NONE | UNKNOWN |
| The app can handle N concurrent calls | Load test against real Azure OpenAI/Speech rate limits and Twilio concurrency limits | NONE — code-level thread/DB-pool ceilings were raised, but never load-tested (see `README.md` §6) | UNKNOWN |

## Cost

| Claim | What would prove it | Current evidence | Status |
|---|---|---|---|
| Cost per call / per resolved call is $X | Real Azure OpenAI + Speech + Twilio billing data across a measured batch of real calls, divided by call count and resolved-call count | NONE — `app/llm/client.py` doesn't even capture token usage yet (see `real_call_procedure.md`'s Known Gap) | UNKNOWN |

## Customer demand

| Claim | What would prove it | Current evidence | Status |
|---|---|---|---|
| A real organization wants this and would pay for it | Actual contact with a prospective pilot customer resulting in expressed interest or a signed pilot agreement | NONE | UNKNOWN |

---

## What this table is for, operationally

Before writing any sentence externally or internally that asserts one of the "Claim" column's statements, check this table first. If the row says `UNKNOWN` or `NOT IMPLEMENTED`, the honest sentence is "we don't know yet" or "this hasn't been tested," not a confident-sounding rephrasing of the claim. Update a row's Status only by adding a specific artifact to its Evidence column — a test name, a report, a dataset, a number with its sample size attached.
