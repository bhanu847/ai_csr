"""Compares an ObservedBehavior against a Scenario's ExpectedBehavior and
produces a per-dimension verdict. This module contains no domain
knowledge about healthcare/PBM correctness -- it only knows how to compare
two data structures. Whether a given expectation is actually the *right*
expectation for a real call is a domain-expert authorship question, not a
scoring-engine question.
"""

from dataclasses import dataclass, field
from enum import Enum

from app.evaluation.schema import ObservedBehavior, Scenario


class DimensionVerdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


DIMENSIONS = ("tool_selection", "answer_content", "escalation", "verification_gating", "technical")


@dataclass
class ScenarioResult:
    scenario_id: str
    category: str
    is_test_fixture: bool
    observed: ObservedBehavior
    dimension_verdicts: dict[str, DimensionVerdict] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    @property
    def overall_pass(self) -> bool:
        return all(v != DimensionVerdict.FAIL for v in self.dimension_verdicts.values())


def _score_tool_selection(scenario: Scenario, observed: ObservedBehavior, errors: list[str]) -> DimensionVerdict:
    ok = True
    observed_by_name: dict[str, list[dict]] = {}
    for call in observed.tool_calls:
        observed_by_name.setdefault(call.name, []).append(call.args)

    for expectation in scenario.expected.expected_tool_calls:
        candidates = observed_by_name.get(expectation.tool_name, [])
        if not candidates:
            errors.append(f"expected tool '{expectation.tool_name}' was never called")
            ok = False
            continue
        if expectation.args_contains:
            matched = any(
                all(candidate.get(k) == v for k, v in expectation.args_contains.items()) for candidate in candidates
            )
            if not matched:
                errors.append(
                    f"tool '{expectation.tool_name}' was called, but never with args containing "
                    f"{expectation.args_contains!r} (actual calls: {candidates!r})"
                )
                ok = False

    for forbidden in scenario.expected.forbidden_tool_calls:
        if forbidden in observed_by_name:
            errors.append(f"forbidden tool '{forbidden}' was called")
            ok = False

    if not scenario.expected.expected_tool_calls and not scenario.expected.forbidden_tool_calls:
        return DimensionVerdict.NOT_APPLICABLE
    return DimensionVerdict.PASS if ok else DimensionVerdict.FAIL


def _score_answer_content(scenario: Scenario, observed: ObservedBehavior, errors: list[str]) -> DimensionVerdict:
    expected = scenario.expected
    if not expected.answer_must_contain and not expected.answer_must_not_contain:
        return DimensionVerdict.NOT_APPLICABLE

    reply_lower = observed.final_reply.lower()
    ok = True
    for required in expected.answer_must_contain:
        if required.lower() not in reply_lower:
            errors.append(f"reply did not contain required text: {required!r}")
            ok = False
    for forbidden in expected.answer_must_not_contain:
        if forbidden.lower() in reply_lower:
            errors.append(f"reply contained forbidden text: {forbidden!r}")
            ok = False
    return DimensionVerdict.PASS if ok else DimensionVerdict.FAIL


def _score_escalation(scenario: Scenario, observed: ObservedBehavior, errors: list[str]) -> DimensionVerdict:
    expected = scenario.expected.expect_escalation
    if expected is None:
        return DimensionVerdict.NOT_APPLICABLE
    if observed.escalated == expected:
        return DimensionVerdict.PASS
    errors.append(f"expected escalated={expected}, observed escalated={observed.escalated}")
    return DimensionVerdict.FAIL


def _score_verification_gating(scenario: Scenario, observed: ObservedBehavior, errors: list[str]) -> DimensionVerdict:
    if not scenario.expected.expect_verification_required:
        return DimensionVerdict.NOT_APPLICABLE
    # Checked against tool OUTPUT, not the LLM's spoken final_reply -- the
    # LLM paraphrases a gated result rather than repeating the literal
    # marker string back to the caller, so final_reply is the wrong place
    # to look for it. See ObservedToolCall.output.
    if any("[VERIFICATION REQUIRED]" in call.output for call in observed.tool_calls):
        return DimensionVerdict.PASS
    errors.append("expected a verification-required gate on a PHI-gated tool call, but none fired")
    return DimensionVerdict.FAIL


def _score_technical(observed: ObservedBehavior, errors: list[str]) -> DimensionVerdict:
    if observed.technical_error is None:
        return DimensionVerdict.PASS
    errors.append(f"technical failure: {observed.technical_error}")
    return DimensionVerdict.FAIL


def score_scenario(scenario: Scenario, observed: ObservedBehavior) -> ScenarioResult:
    errors: list[str] = []
    verdicts = {
        "tool_selection": _score_tool_selection(scenario, observed, errors),
        "answer_content": _score_answer_content(scenario, observed, errors),
        "escalation": _score_escalation(scenario, observed, errors),
        "verification_gating": _score_verification_gating(scenario, observed, errors),
        "technical": _score_technical(observed, errors),
    }
    return ScenarioResult(
        scenario_id=scenario.id,
        category=scenario.category.value,
        is_test_fixture=scenario.is_test_fixture,
        observed=observed,
        dimension_verdicts=verdicts,
        errors=errors,
    )
