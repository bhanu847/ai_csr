"""Aggregation and reporting over a list of ScenarioResult.

Deliberately refuses to blend is_test_fixture=True results into the same
summary as real scenario results -- a report mixing "5 harness-proving
fixtures, all passing" with "here is our domain accuracy" would be exactly
the kind of overclaim this framework exists to prevent.
"""

import json
from dataclasses import asdict
from datetime import datetime, timezone

from app.evaluation.scoring import DIMENSIONS, DimensionVerdict, ScenarioResult


class MixedFixtureAndRealResultsError(Exception):
    pass


def _check_not_mixed(results: list[ScenarioResult]) -> None:
    fixture_flags = {r.is_test_fixture for r in results}
    if len(fixture_flags) > 1:
        raise MixedFixtureAndRealResultsError(
            "Refusing to aggregate test-fixture results together with real scenario results in one "
            "report -- call aggregate() separately for each group (filter by is_test_fixture)."
        )


def aggregate(results: list[ScenarioResult]) -> dict:
    if not results:
        return {"scenario_count": 0, "is_test_fixture": None, "overall_pass_rate": None, "by_category": {}, "by_dimension": {}}

    _check_not_mixed(results)
    is_test_fixture = results[0].is_test_fixture

    by_category: dict[str, dict] = {}
    for r in results:
        cat = by_category.setdefault(r.category, {"total": 0, "passed": 0})
        cat["total"] += 1
        if r.overall_pass:
            cat["passed"] += 1

    by_dimension: dict[str, dict] = {}
    for dim in DIMENSIONS:
        applicable = [r for r in results if r.dimension_verdicts.get(dim) != DimensionVerdict.NOT_APPLICABLE]
        passed = [r for r in applicable if r.dimension_verdicts.get(dim) == DimensionVerdict.PASS]
        by_dimension[dim] = {
            "applicable": len(applicable),
            "passed": len(passed),
            "pass_rate": (len(passed) / len(applicable)) if applicable else None,
        }

    overall_passed = sum(1 for r in results if r.overall_pass)
    latencies = [r.observed.latency_ms for r in results if r.observed.latency_ms is not None]
    costs = [r.observed.cost_usd for r in results if r.observed.cost_usd is not None]

    return {
        "scenario_count": len(results),
        "is_test_fixture": is_test_fixture,
        "overall_pass_rate": overall_passed / len(results),
        "by_category": by_category,
        "by_dimension": by_dimension,
        "avg_latency_ms": (sum(latencies) / len(latencies)) if latencies else None,
        "avg_cost_usd": (sum(costs) / len(costs)) if costs else None,
        "cost_data_available": bool(costs),
    }


def render_report(results: list[ScenarioResult]) -> str:
    summary = aggregate(results)
    lines = []

    if summary["is_test_fixture"]:
        lines.append("=" * 70)
        lines.append("HARNESS TEST FIXTURES -- NOT domain validation. These scenarios exist")
        lines.append("only to prove the evaluation harness mechanics work correctly.")
        lines.append("=" * 70)
    else:
        lines.append("=" * 70)
        lines.append("EVALUATION RESULTS")
        lines.append("=" * 70)

    lines.append(f"Scenarios run: {summary['scenario_count']}")
    if summary["overall_pass_rate"] is not None:
        lines.append(f"Overall pass rate: {summary['overall_pass_rate']:.1%}")

    lines.append("\nBy category:")
    for cat, stats in summary["by_category"].items():
        lines.append(f"  {cat}: {stats['passed']}/{stats['total']} passed")

    lines.append("\nBy dimension:")
    for dim, stats in summary["by_dimension"].items():
        if stats["applicable"] == 0:
            lines.append(f"  {dim}: not applicable to any scenario in this run")
        else:
            lines.append(f"  {dim}: {stats['passed']}/{stats['applicable']} passed ({stats['pass_rate']:.1%})")

    if summary["avg_latency_ms"] is not None:
        lines.append(f"\nAvg latency: {summary['avg_latency_ms']:.0f}ms")

    if summary["cost_data_available"]:
        lines.append(f"Avg cost: ${summary['avg_cost_usd']:.4f}/call")
    else:
        lines.append("Cost: NOT AVAILABLE -- app/llm/client.py doesn't return token usage yet")

    failures = [r for r in results if not r.overall_pass]
    if failures:
        lines.append(f"\nFailures ({len(failures)}):")
        for r in failures:
            lines.append(f"  [{r.scenario_id}] {'; '.join(r.errors)}")

    return "\n".join(lines)


def to_json(results: list[ScenarioResult]) -> str:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": aggregate(results),
        "results": [
            {
                "scenario_id": r.scenario_id,
                "category": r.category,
                "is_test_fixture": r.is_test_fixture,
                "overall_pass": r.overall_pass,
                "dimension_verdicts": {k: v.value for k, v in r.dimension_verdicts.items()},
                "errors": r.errors,
                # asdict() recurses into ObservedToolCall automatically since
                # it's a dataclass too -- no manual tool_calls conversion needed.
                "observed": asdict(r.observed),
            }
            for r in results
        ],
    }
    return json.dumps(payload, indent=2, default=str)
