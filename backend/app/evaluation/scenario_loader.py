"""Loads Scenario objects from a JSON file authored by a domain expert who
is not a Python programmer -- see docs/validation/scenario_authoring_guide.md
for the format, and app/evaluation/scenario_template.json for a filled-in
example.

This module has no opinion about whether a loaded scenario is realistic or
correct -- that's the authoring expert's responsibility, not this loader's.
It only enforces that the file is *structurally* valid (required fields
present, category is a real ScenarioCategory, etc.) and fails loudly on
anything malformed rather than silently dropping or guessing at bad rows.

Scenarios loaded through here default to is_test_fixture=False -- they are
meant to be real domain-validation scenarios, not harness fixtures. A file
can still mark individual entries is_test_fixture: true if someone wants to
draft/test the format itself without it being mistaken for validated
domain content.
"""

import json
from pathlib import Path

from app.evaluation.schema import (
    ExpectedBehavior,
    Scenario,
    ScenarioCategory,
    ScenarioTurn,
    ToolCallExpectation,
)


class ScenarioFileError(Exception):
    """Raised on any structurally invalid scenario file -- missing field,
    unknown category, wrong type, etc. Deliberately fails the whole file
    rather than silently skipping the bad entry, so a typo can't quietly
    shrink the evaluation set without anyone noticing."""


def _require(d: dict, key: str, scenario_index: int) -> object:
    if key not in d:
        raise ScenarioFileError(f"scenario at index {scenario_index}: missing required field '{key}'")
    return d[key]


def _parse_tool_call_expectation(d: dict, scenario_index: int) -> ToolCallExpectation:
    if "tool_name" not in d:
        raise ScenarioFileError(
            f"scenario at index {scenario_index}: expected_tool_calls entry missing 'tool_name'"
        )
    return ToolCallExpectation(tool_name=d["tool_name"], args_contains=d.get("args_contains"))


def _parse_expected(d: dict, scenario_index: int) -> ExpectedBehavior:
    return ExpectedBehavior(
        expected_tool_calls=[
            _parse_tool_call_expectation(t, scenario_index) for t in d.get("expected_tool_calls", [])
        ],
        forbidden_tool_calls=d.get("forbidden_tool_calls", []),
        answer_must_contain=d.get("answer_must_contain", []),
        answer_must_not_contain=d.get("answer_must_not_contain", []),
        expect_escalation=d.get("expect_escalation"),
        expect_verification_required=d.get("expect_verification_required", False),
        notes=d.get("notes", ""),
    )


def _parse_scenario(d: dict, scenario_index: int) -> Scenario:
    scenario_id = _require(d, "id", scenario_index)
    category_raw = _require(d, "category", scenario_index)
    try:
        category = ScenarioCategory(category_raw)
    except ValueError as exc:
        valid = ", ".join(c.value for c in ScenarioCategory)
        raise ScenarioFileError(
            f"scenario '{scenario_id}': invalid category '{category_raw}' -- must be one of: {valid}"
        ) from exc

    turns_raw = _require(d, "turns", scenario_index)
    if not turns_raw:
        raise ScenarioFileError(f"scenario '{scenario_id}': turns must have at least one entry")
    turns = [ScenarioTurn(customer_utterance=t) for t in turns_raw]

    expected_raw = _require(d, "expected", scenario_index)
    expected = _parse_expected(expected_raw, scenario_index)

    return Scenario(
        id=scenario_id,
        description=d.get("description", ""),
        category=category,
        turns=turns,
        expected=expected,
        is_test_fixture=d.get("is_test_fixture", False),
    )


def load_scenarios_from_file(path: str | Path) -> list[Scenario]:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScenarioFileError(f"{path}: not valid JSON -- {exc}") from exc

    if not isinstance(raw, list):
        raise ScenarioFileError(f"{path}: top-level JSON must be a list of scenario objects")

    scenarios = [_parse_scenario(entry, i) for i, entry in enumerate(raw)]

    ids = [s.id for s in scenarios]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ScenarioFileError(f"{path}: duplicate scenario id(s): {sorted(duplicates)}")

    return scenarios
