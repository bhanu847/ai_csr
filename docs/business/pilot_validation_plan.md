# Pilot Validation Plan

**What this document is:** a preparation framework — an ideal customer profile, a pilot structure, a value proposition draft, discovery questions, and a measurement plan — so that outreach can start without improvising the basics each time.

**What this document is NOT:** evidence of customer demand. No organization has been contacted. No one has expressed interest. Nothing in this document should be read, quoted, or repeated as "we have prospects" or "customers want this." Every mention of a company *type* below is a targeting criterion, not a named prospect. The moment real contact happens, that goes in a separate, dated record — not this file.

---

## Ideal Customer Profile (ICP)

Criteria, in priority order:

1. **Real, recurring call volume in a narrow, repetitive category** — specifically prescription/pharmacy-benefit/claim-support calls, matching the one workflow this product is built to handle well. High volume of genuinely varied call types is a worse fit than moderate volume of repetitive ones.
2. **Real, felt cost pain from that call volume** — currently staffing a call center or paying a BPO for it, and that cost is large enough that a measurable percentage reduction matters to someone with budget authority.
3. **Organizationally able to move fast** — not gated behind the multi-year vendor-security-review process a national insurer or top-5 PBM would require. This points toward smaller/mid-size organizations, not the largest players, at least for a first pilot.
4. **Willing to pilot with real (or realistically de-identified) call scenarios and give honest feedback on failures** — a customer who wants a polished demo, not a genuine test, is the wrong first customer regardless of size.
5. **Has *some* tolerance for imperfection in exchange for cost savings and being an early mover** — a completely risk-averse organization is not a good first pilot, independent of size.

**Company types that plausibly fit these criteria** (categories, not leads):
- Regional third-party administrators (TPAs)
- Healthcare business process outsourcers (BPOs) that staff PBM/insurance call centers for others
- Specialty pharmacies
- Regional/smaller health plans or benefits administrators
- Provider organizations with a member-support call line

**Explicitly not a first-pilot target:** large national PBMs/insurers (CVS Caremark, Optum, Express Scripts, etc.) or any organization whose procurement process is known to take multiple quarters before a pilot could even start. Revisit this once there's a proven pilot result to point to.

## Pilot structure

A proposed shape, to be adjusted once a real prospect's constraints are known:

1. **Scope** — one workflow only: prescription/pharmacy-benefit/claim-support calls, using the six-step flow already built (verify → benefits/formulary/claim/pharmacy lookup → resolve or escalate).
2. **Duration** — time-boxed, e.g. 4–8 weeks, not open-ended.
3. **Volume** — starts on a subset of real (or shadow/parallel, not yet caller-facing) call volume, scaling only after each stage's results are reviewed — mirroring the 1 → 10 → 100 → 500 progression in `docs/validation/real_call_procedure.md`.
4. **Data** — either the pilot customer's own data connected through the `PBMProvider` interface (see `app/pbm/provider.py`) once a real adapter exists for their system, or a jointly-agreed synthetic/de-identified dataset if a real integration isn't ready in time. Never claim a live pilot uses a real integration unless it actually does.
5. **Success criteria** — agreed *before* the pilot starts, not retrofitted afterward. Should include specific numbers for containment rate, resolution correctness, and cost per call, matching the format in `docs/validation/evidence_requirements.md`.
6. **Exit criteria** — what happens if the pilot doesn't hit the bar: a defined stop, not an indefinite extension.

## Value proposition (draft, to be refined per prospect)

> An AI voice agent that handles routine prescription, pharmacy benefit, and claim-support calls — verifying member identity, retrieving authoritative plan information, executing approved actions, and escalating anything it isn't confident about — at a fraction of the per-minute cost of a human agent, with a complete transcript and audit trail for every call.

Do not quote a specific cost-savings percentage or containment rate to a prospect until the pilot has actually produced one — see `docs/validation/evidence_requirements.md`. Before a pilot's own numbers exist, speak in terms of what will be measured, not a promised outcome.

## Discovery questions for a prospect conversation

Aimed at testing ICP fit and surfacing real requirements, not at selling:

- What percentage of your inbound call volume falls into prescription/benefit/claim-status categories specifically?
- What does a call in that category cost you today, fully loaded (staffing, BPO fees, overhead)?
- What system(s) would member/claims/formulary/pharmacy data need to come from? Is there an API, or would this require custom integration work?
- What's your compliance/security review process, and how long does it typically take for a new vendor?
- Would you be willing to pilot against a subset of real call volume, or would this need to start with synthetic/shadow testing first?
- Who internally would need to sign off on a pilot, and what would they need to see to say yes?
- What would "this pilot worked" concretely look like to you — what number, measured how?
- What's your appetite for the AI being wrong sometimes during a pilot, given it's explicitly time-boxed and measured?

## Pilot measurement plan

Reuses the framework already built, not a separate system:

- Every pilot call is scored on the same dimensions as `app/evaluation/scoring.py`: tool selection, answer content, escalation correctness, verification gating, technical reliability.
- Aggregate results via `app/evaluation/report.py`, kept separate from any harness-fixture or synthetic-scenario results (the framework already refuses to blend these — see `MixedFixtureAndRealResultsError`).
- Reported to the pilot customer using the same evidence-based language as `docs/validation/evidence_requirements.md` — a number with its sample size and method, never a rounded-up narrative claim.
- Cost is calculated from actual Azure/Twilio billing for the pilot's real call volume, not estimated.

## Status of this plan

Nothing below this line has happened yet:
- [ ] No prospect has been contacted
- [ ] No discovery call has occurred
- [ ] No pilot agreement exists
- [ ] No real customer data has been discussed, let alone connected

This document becomes useful the moment outreach starts — until then, it's preparation, and should never be characterized as anything more.
