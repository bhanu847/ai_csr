# Scenario Authoring Guide

**Who this is for:** a PBM/healthcare domain expert writing real test scenarios for the AI to be evaluated against. You do not need to write or read code — you're filling in a structured template, one scenario at a time.

**What this is NOT for:** this guide describes the *format*. It does not tell you what scenarios to write — that's the domain expertise this process needs and the engineering side of this project explicitly does not have. See the "What makes a good scenario" section below for guidance, but the actual content (what a caller realistically says, what the correct answer is, what counts as a safety violation) has to come from you.

---

## The file format

Scenarios live in a JSON file — a list of scenario entries. Start from `backend/app/evaluation/scenario_template.json`, which has one filled-in example clearly marked as a placeholder. Copy that entry, replace every field, and repeat for each scenario. Multiple scenarios go in the same list.

## Fields, explained

| Field | Required? | What it means |
|---|---|---|
| `id` | Yes | A short unique name for this scenario, e.g. `"claim-rejected-pa-required-001"`. Must not repeat across the file. |
| `description` | No, but strongly recommended | One sentence: what is this scenario testing and why does it matter. |
| `category` | Yes | One of: `normal`, `identity_failure`, `ambiguous`, `safety`, `conversation`, `technical`. See categories below. |
| `turns` | Yes, at least one | A list of strings — what the caller says, in order. One entry = a single-turn scenario; multiple entries = a back-and-forth conversation (e.g. verify, then ask a follow-up). |
| `expected` | Yes | The block describing what the *correct* behavior looks like — see below. |
| `is_test_fixture` | No, defaults to `false` | Leave this as `false` (or omit it) for real scenarios. Only set `true` if you're testing the format itself, not authoring a real scenario — a `true` scenario is excluded from real evaluation reports. |

### The `expected` block

| Field | What it means |
|---|---|
| `expected_tool_calls` | List of tools the AI should call for this scenario to be correct. Each entry has `tool_name` (required) and optionally `args_contains` — specific argument values you expect (e.g. `{"drug_name": "Humira"}`). Real tool names: `verify_member`, `check_claim_status`, `get_benefits`, `search_formulary`, `find_pharmacy`, `search_documents`, `create_ticket`, `schedule_callback`, `schedule_appointment`, `escalate_to_human`, `update_customer`, `send_email`. |
| `forbidden_tool_calls` | Tools that must NOT be called — e.g. a claims lookup happening before verification would be a real bug. |
| `answer_must_contain` | Substrings the AI's spoken reply should contain if it answered correctly. Case-insensitive. Keep these to the essential fact, not exact phrasing — the AI won't use your exact words. |
| `answer_must_not_contain` | Substrings that would indicate a wrong or unsafe answer — **this is where PHI-safety and hallucination checks live.** E.g. if a scenario's correct answer is "I don't have that information," you might list the *wrong* answer's key fact here so the scorer catches it if the AI invents one. |
| `expect_escalation` | `true` if this scenario should end with the AI escalating to a human, `false` if it definitely should NOT, omit/`null` if not relevant to this scenario. |
| `expect_verification_required` | `true` if the correct behavior is for the AI to decline and ask for verification (e.g. a claims question with no prior verify_member call). |
| `notes` | Required. Explain your reasoning — why is this the correct expected behavior? This is what lets someone else (or you, in six months) understand the scenario without re-deriving it. |

## Categories

Use these to make sure the scenario set has real coverage, not just a pile of easy cases:

- **normal** — realistic, answerable calls (covered/non-covered medication, claim approved/rejected/pending, pharmacy lookup, benefits question).
- **identity_failure** — wrong member ID, wrong DOB, wrong ZIP, incomplete verification, caller refuses to verify.
- **ambiguous** — unclear medication name, vague claim reference, a question with multiple reasonable interpretations.
- **safety** — caller asks for someone else's information, tries to talk around verification, asks something with insufficient source information, or where information conflicts.
- **conversation** — interruption, the caller correcting themselves, switching topics mid-call, repeating a question, expressing frustration, asking for a human, a long pause.
- **technical** — what should happen if a tool times out, the database is unreachable, STT fails, the LLM errors, TTS fails. (These are harder to script as a simple JSON scenario since they need a fault to actually be injected — flag these to engineering rather than trying to force them into the same format if the format doesn't fit.)

## What makes a good scenario

- **Specific, not generic.** "Caller asks about a claim" is not enough — a real caller says something like a real caller would say it, with the messiness real callers have (partial information, a slightly wrong claim number, background noise implied by a garbled request).
- **One clear correct answer.** If two domain experts would disagree about what the AI should do here, that's a real and useful finding — but flag it as such in `notes` rather than picking one answer arbitrarily.
- **PHI-safety scenarios need a wrong answer defined, not just a right one.** The most valuable safety scenarios are ones where an AI that's slightly too eager would get it wrong (revealing info before full verification, confirming a fact about "your spouse's claim" that it can't actually verify belongs to the caller).
- **Don't only write easy cases.** A scenario set that's 90% straightforward "covered medication" questions won't tell you anything about where the AI actually breaks. Deliberately include edge cases even though they're harder to write.

## Validating your file

Before treating a batch of scenarios as ready, run:

```bash
cd backend
venv/Scripts/python.exe -c "
from app.evaluation.scenario_loader import load_scenarios_from_file
scenarios = load_scenarios_from_file('path/to/your_scenarios.json')
print(f'Loaded {len(scenarios)} scenarios OK')
"
```

This only checks the file is *structurally* valid (every required field present, categories spelled correctly, no duplicate IDs) — it does not check whether your scenarios are good ones. That validation only ever comes from another domain expert reviewing them.

## What happens after scenarios are authored

Once a file of real scenarios exists and Azure credentials are unblocked, they get run through `RealPipelineExecutor` (see `app/evaluation/runner.py`) and scored the same way the harness fixtures already are — see `scripts/run_evaluation.py` for the pattern. The results feed directly into the "Accuracy" and related rows of `docs/validation/evidence_requirements.md`. Nothing about scenarios written this way is treated as validated domain truth until that run has actually happened and been reviewed.
