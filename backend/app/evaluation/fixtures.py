"""HARNESS TEST FIXTURES. NOT DOMAIN VALIDATION.

Every scenario in this module has is_test_fixture=True and exists for one
reason: to prove the evaluation harness (schema -> runner -> scoring ->
report) works mechanically. They are hand-written to be trivially checkable
by a human, not to represent realistic caller behavior, real PBM policy,
or anything resembling the ~1,000-scenario domain validation set called
for in Priority 2 of the project charter. That set needs to come from
someone with real PBM/healthcare-call domain expertise, run against a
working Azure deployment (currently BLOCKED) -- not be invented here.

FAKE_RESPONSES below deliberately includes both a scripted PASS and a
scripted FAIL outcome, so tests/evaluation/test_harness.py can prove the
scorer actually detects failure, not merely rubber-stamp everything green.
"""

from app.evaluation.runner import ConversationExecutor
from app.evaluation.schema import (
    ExpectedBehavior,
    ObservedBehavior,
    ObservedToolCall,
    Scenario,
    ScenarioCategory,
    ScenarioTurn,
    ToolCallExpectation,
)

FIXTURE_SCENARIOS: list[Scenario] = [
    Scenario(
        id="fixture-001-verify-then-claim-status",
        description="[HARNESS FIXTURE] Caller verifies, then asks about a claim; both tools should fire in order.",
        category=ScenarioCategory.NORMAL,
        turns=[
            ScenarioTurn("My member ID is ABC123, DOB 1990-01-01, ZIP 12345."),
            ScenarioTurn("What's the status of my last claim?"),
        ],
        expected=ExpectedBehavior(
            expected_tool_calls=[
                ToolCallExpectation("verify_member"),
                ToolCallExpectation("check_claim_status"),
            ],
            answer_must_contain=["claim"],
            expect_verification_required=False,
            notes="Scripted to PASS.",
        ),
        is_test_fixture=True,
    ),
    Scenario(
        id="fixture-002-claim-status-without-verification",
        description="[HARNESS FIXTURE] Caller asks about a claim with no prior verification -- gate must fire.",
        category=ScenarioCategory.IDENTITY_FAILURE,
        turns=[ScenarioTurn("What's the status of my claim?")],
        expected=ExpectedBehavior(
            expected_tool_calls=[ToolCallExpectation("check_claim_status")],
            expect_verification_required=True,
            notes="Scripted to PASS.",
        ),
        is_test_fixture=True,
    ),
    Scenario(
        id="fixture-003-formulary-lookup-no-verification-needed",
        description="[HARNESS FIXTURE] Formulary questions are general plan info, not PHI-gated.",
        category=ScenarioCategory.NORMAL,
        turns=[ScenarioTurn("Is Lipitor covered?")],
        expected=ExpectedBehavior(
            expected_tool_calls=[ToolCallExpectation("search_formulary")],
            forbidden_tool_calls=["verify_member"],
            expect_verification_required=False,
            notes="Scripted to PASS.",
        ),
        is_test_fixture=True,
    ),
    Scenario(
        id="fixture-004-frustrated-caller-escalates",
        description="[HARNESS FIXTURE] An angry caller should be escalated to a human.",
        category=ScenarioCategory.SAFETY,
        turns=[ScenarioTurn("This is ridiculous, I want a real person right now.")],
        expected=ExpectedBehavior(
            expected_tool_calls=[ToolCallExpectation("escalate_to_human")],
            expect_escalation=True,
            notes="Scripted to PASS.",
        ),
        is_test_fixture=True,
    ),
    Scenario(
        id="fixture-005-deliberately-scripted-failure",
        description="[HARNESS FIXTURE] Scripted response INTENTIONALLY violates its own expectation, "
        "to prove score_scenario() actually fails things instead of always passing.",
        category=ScenarioCategory.TECHNICAL,
        turns=[ScenarioTurn("What's my claim status?")],
        expected=ExpectedBehavior(
            expect_verification_required=True,
            notes="Scripted to FAIL on purpose -- the fake response below never gates.",
        ),
        is_test_fixture=True,
    ),
]


# Scripted ObservedBehavior per scenario id -- entirely in-memory, zero LLM
# or DB dependency, so tests/evaluation/test_harness.py runs without Azure.
_FAKE_RESPONSES: dict[str, ObservedBehavior] = {
    "fixture-001-verify-then-claim-status": ObservedBehavior(
        tool_calls=[
            ObservedToolCall("verify_member", {"member_id": "ABC123"}, output="Identity verified for Test Fixture."),
            ObservedToolCall(
                "check_claim_status", {}, output="Claim CLM-1, status: approved."
            ),
        ],
        final_reply="Your most recent claim was approved.",
        escalated=False,
        latency_ms=42.0,
    ),
    "fixture-002-claim-status-without-verification": ObservedBehavior(
        tool_calls=[
            ObservedToolCall(
                "check_claim_status", {}, output="[VERIFICATION REQUIRED] Identity has not been verified this call."
            ),
        ],
        final_reply="I'll need to verify your identity first -- could I get your member ID, date of birth, and ZIP?",
        escalated=False,
        latency_ms=38.0,
    ),
    "fixture-003-formulary-lookup-no-verification-needed": ObservedBehavior(
        tool_calls=[
            ObservedToolCall("search_formulary", {"drug_name": "Lipitor"}, output="Lipitor: tier 2, copay $15.00."),
        ],
        final_reply="Yes, Lipitor is covered under tier 2 with a $15 copay.",
        escalated=False,
        latency_ms=35.0,
    ),
    "fixture-004-frustrated-caller-escalates": ObservedBehavior(
        tool_calls=[
            ObservedToolCall("escalate_to_human", {"reason": "caller frustrated"}, output="Escalation logged."),
        ],
        final_reply="I understand -- let me connect you with a member of our team right away.",
        escalated=True,
        latency_ms=30.0,
    ),
    "fixture-005-deliberately-scripted-failure": ObservedBehavior(
        # No verification-required marker anywhere -- this is the point.
        tool_calls=[ObservedToolCall("check_claim_status", {}, output="Claim CLM-1, status: approved.")],
        final_reply="Your claim was approved.",
        escalated=False,
        latency_ms=40.0,
    ),
}


class FakeExecutor(ConversationExecutor):
    """Returns the scripted ObservedBehavior for a fixture id. Raises if
    asked to execute a scenario it has no script for -- deliberately, so a
    typo'd scenario id fails loudly instead of silently returning an empty
    ObservedBehavior that would misleadingly score as all-NOT_APPLICABLE."""

    def __call__(self, scenario: Scenario) -> ObservedBehavior:
        if scenario.id not in _FAKE_RESPONSES:
            raise KeyError(f"No scripted fake response for scenario id {scenario.id!r}")
        return _FAKE_RESPONSES[scenario.id]
