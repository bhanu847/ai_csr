"""Proves the evaluation harness mechanics (runner -> scoring -> report)
work correctly, using the small labeled fixture set in
app/evaluation/fixtures.py and FakeExecutor -- no Azure, no LLM, no live
database dependency for scoring itself. This is deliberately NOT a test of
domain accuracy; it's a test that the harness correctly computes pass/fail
given known inputs and known expected outputs.

The critical property under test: the scorer must correctly FAIL a
scenario whose scripted outcome violates its own expectation, not just
rubber-stamp everything green. fixture-005 exists specifically for this.
"""

from app.evaluation.fixtures import FIXTURE_SCENARIOS, FakeExecutor
from app.evaluation.report import MixedFixtureAndRealResultsError, aggregate, render_report, to_json
from app.evaluation.runner import run_scenario
from app.evaluation.scoring import DimensionVerdict, score_scenario


def _run_all():
    executor = FakeExecutor()
    return [score_scenario(s, run_scenario(s, executor)) for s in FIXTURE_SCENARIOS]


def test_all_fixtures_are_marked_as_test_fixtures():
    """Guards against a fixture accidentally being authored without the
    label that keeps it out of real evaluation reports."""
    for scenario in FIXTURE_SCENARIOS:
        assert scenario.is_test_fixture is True, f"{scenario.id} must have is_test_fixture=True"


def test_normal_verify_then_claim_passes():
    results = {r.scenario_id: r for r in _run_all()}
    r = results["fixture-001-verify-then-claim-status"]
    assert r.overall_pass is True
    assert r.dimension_verdicts["tool_selection"] == DimensionVerdict.PASS
    assert r.dimension_verdicts["answer_content"] == DimensionVerdict.PASS


def test_verification_gate_scenario_passes_when_gate_fires():
    results = {r.scenario_id: r for r in _run_all()}
    r = results["fixture-002-claim-status-without-verification"]
    assert r.overall_pass is True
    assert r.dimension_verdicts["verification_gating"] == DimensionVerdict.PASS


def test_formulary_lookup_requires_no_verification():
    results = {r.scenario_id: r for r in _run_all()}
    r = results["fixture-003-formulary-lookup-no-verification-needed"]
    assert r.overall_pass is True
    assert r.dimension_verdicts["tool_selection"] == DimensionVerdict.PASS


def test_frustrated_caller_escalation_passes():
    results = {r.scenario_id: r for r in _run_all()}
    r = results["fixture-004-frustrated-caller-escalates"]
    assert r.overall_pass is True
    assert r.dimension_verdicts["escalation"] == DimensionVerdict.PASS


def test_scorer_actually_detects_a_failure():
    """The single most important test in this file: proves score_scenario
    fails a scenario when the scripted behavior violates its expectation,
    rather than always returning PASS regardless of input."""
    results = {r.scenario_id: r for r in _run_all()}
    r = results["fixture-005-deliberately-scripted-failure"]

    assert r.overall_pass is False
    assert r.dimension_verdicts["verification_gating"] == DimensionVerdict.FAIL
    assert len(r.errors) > 0
    assert "verification-required" in r.errors[0].lower()


def test_fake_executor_raises_on_unknown_scenario_id():
    from app.evaluation.fixtures import FakeExecutor
    from app.evaluation.schema import ExpectedBehavior, Scenario, ScenarioCategory, ScenarioTurn

    unknown = Scenario(
        id="not-in-the-script",
        description="test",
        category=ScenarioCategory.TECHNICAL,
        turns=[ScenarioTurn("hello")],
        expected=ExpectedBehavior(),
    )
    # run_scenario() catches the exception and turns it into a
    # technical_error rather than propagating -- so the harness never
    # crashes on one bad scenario, and that failure is itself observable.
    observed = run_scenario(unknown, FakeExecutor())
    assert observed.technical_error is not None
    assert "No scripted fake response" in observed.technical_error


def test_aggregate_counts_are_correct():
    results = _run_all()
    summary = aggregate(results)

    assert summary["scenario_count"] == 5
    assert summary["is_test_fixture"] is True
    assert summary["overall_pass_rate"] == 4 / 5  # 4 pass, 1 deliberately fails
    assert summary["by_category"]["normal"]["total"] == 2
    assert summary["by_category"]["technical"]["passed"] == 0


def test_aggregate_refuses_to_mix_fixture_and_real_results():
    results = _run_all()
    real_scenario = FIXTURE_SCENARIOS[0]
    real_scenario_copy = score_scenario(real_scenario, run_scenario(real_scenario, FakeExecutor()))
    real_scenario_copy.is_test_fixture = False  # simulate a real (non-fixture) result

    try:
        aggregate([*results, real_scenario_copy])
        raised = False
    except MixedFixtureAndRealResultsError:
        raised = True
    assert raised, "aggregate() must refuse to blend fixture and real results into one summary"


def test_render_report_labels_fixture_runs_clearly():
    report = render_report(_run_all())
    assert "NOT domain validation" in report
    assert "fixture-005" in report  # the known failure shows up in the failures section


def test_to_json_round_trips():
    import json

    payload = json.loads(to_json(_run_all()))
    assert payload["summary"]["scenario_count"] == 5
    assert len(payload["results"]) == 5
    assert any(r["scenario_id"] == "fixture-005-deliberately-scripted-failure" and not r["overall_pass"] for r in payload["results"])
