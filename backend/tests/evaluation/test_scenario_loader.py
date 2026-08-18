"""Proves the scenario loader correctly parses a valid file, fails loudly
on structurally invalid input, and that a loaded scenario is fully
compatible with the rest of the evaluation harness (runner + scoring) --
not just that it parses.
"""

import json
from pathlib import Path

import pytest

from app.evaluation.report import aggregate
from app.evaluation.runner import ConversationExecutor, run_scenario
from app.evaluation.schema import ObservedBehavior, ObservedToolCall, ScenarioCategory
from app.evaluation.scenario_loader import ScenarioFileError, load_scenarios_from_file
from app.evaluation.scoring import score_scenario

TEMPLATE_PATH = Path(__file__).resolve().parent.parent.parent / "app" / "evaluation" / "scenario_template.json"


def test_template_file_loads_structurally():
    """Proves the shipped template stays in sync with the loader's actual
    schema -- if someone changes one without the other, this fails."""
    scenarios = load_scenarios_from_file(TEMPLATE_PATH)
    assert len(scenarios) == 1
    assert scenarios[0].id == "TEMPLATE-EXAMPLE-001"
    assert "TEMPLATE EXAMPLE ONLY" in scenarios[0].description


def test_load_valid_multi_scenario_file(tmp_path):
    data = [
        {
            "id": "real-001",
            "description": "example",
            "category": "normal",
            "turns": ["hello"],
            "expected": {
                "expected_tool_calls": [{"tool_name": "search_formulary", "args_contains": {"drug_name": "X"}}],
                "answer_must_contain": ["covered"],
                "notes": "test",
            },
        },
        {
            "id": "real-002",
            "description": "example 2",
            "category": "identity_failure",
            "turns": ["what's my claim status"],
            "expected": {"expect_verification_required": True, "notes": "test"},
        },
    ]
    path = tmp_path / "scenarios.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    scenarios = load_scenarios_from_file(path)

    assert len(scenarios) == 2
    assert scenarios[0].id == "real-001"
    assert scenarios[0].category == ScenarioCategory.NORMAL
    assert scenarios[0].is_test_fixture is False  # default for loaded (real) scenarios
    assert scenarios[0].expected.expected_tool_calls[0].tool_name == "search_formulary"
    assert scenarios[0].expected.expected_tool_calls[0].args_contains == {"drug_name": "X"}
    assert scenarios[1].expected.expect_verification_required is True


def test_missing_required_field_raises_with_clear_message(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([{"id": "x", "category": "normal", "expected": {}}]), encoding="utf-8")  # no "turns"

    with pytest.raises(ScenarioFileError, match="turns"):
        load_scenarios_from_file(path)


def test_invalid_category_raises_with_valid_options_listed(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps([{"id": "x", "category": "not_a_real_category", "turns": ["hi"], "expected": {}}]),
        encoding="utf-8",
    )

    with pytest.raises(ScenarioFileError, match="invalid category"):
        load_scenarios_from_file(path)


def test_duplicate_ids_raise(tmp_path):
    entry = {"id": "dup", "category": "normal", "turns": ["hi"], "expected": {}}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([entry, entry]), encoding="utf-8")

    with pytest.raises(ScenarioFileError, match="duplicate"):
        load_scenarios_from_file(path)


def test_malformed_json_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{ this is not valid json", encoding="utf-8")

    with pytest.raises(ScenarioFileError, match="not valid JSON"):
        load_scenarios_from_file(path)


def test_non_list_top_level_raises(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"id": "x"}), encoding="utf-8")

    with pytest.raises(ScenarioFileError, match="must be a list"):
        load_scenarios_from_file(path)


def test_loaded_scenario_runs_through_the_full_harness(tmp_path):
    """A loaded scenario isn't just parseable -- it has to actually work
    with run_scenario/score_scenario/aggregate, same as a fixture would."""
    data = [
        {
            "id": "real-e2e-001",
            "description": "end-to-end loader compatibility check",
            "category": "normal",
            "turns": ["is metformin covered"],
            "expected": {
                "expected_tool_calls": [{"tool_name": "search_formulary"}],
                "answer_must_contain": ["covered"],
                "notes": "test",
            },
        }
    ]
    path = tmp_path / "scenarios.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    scenarios = load_scenarios_from_file(path)

    class _Executor(ConversationExecutor):
        def __call__(self, scenario):
            return ObservedBehavior(
                tool_calls=[ObservedToolCall("search_formulary", {"drug_name": "metformin"}, output="tier 1")],
                final_reply="Metformin is covered under tier 1.",
            )

    results = [score_scenario(s, run_scenario(s, _Executor())) for s in scenarios]
    assert results[0].overall_pass is True

    summary = aggregate(results)
    assert summary["is_test_fixture"] is False  # proves loaded scenarios are NOT mistaken for fixtures
