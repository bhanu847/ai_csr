"""Scenario and expected-behavior schema for the evaluation framework.

IMPORTANT: no scenarios describing real healthcare/PBM call behavior live
in this module or anywhere in app/evaluation/. This module defines the
SHAPE a scenario takes; app/evaluation/fixtures.py contains only a small,
explicitly-labeled set of fixtures that exist to prove the harness itself
works, not to represent validated domain behavior. Real scenarios need
domain expert authorship and are out of scope for this pass -- see the
module docstring on fixtures.py.
"""

from dataclasses import dataclass, field
from enum import Enum


class ScenarioCategory(str, Enum):
    NORMAL = "normal"
    IDENTITY_FAILURE = "identity_failure"
    AMBIGUOUS = "ambiguous"
    SAFETY = "safety"
    CONVERSATION = "conversation"
    TECHNICAL = "technical"


@dataclass
class ToolCallExpectation:
    tool_name: str
    # Subset match: every key/value here must appear in the actual call's
    # args, but the actual call may have additional args. None = only the
    # tool name is checked, not its arguments.
    args_contains: dict | None = None


@dataclass
class ExpectedBehavior:
    expected_tool_calls: list[ToolCallExpectation] = field(default_factory=list)
    forbidden_tool_calls: list[str] = field(default_factory=list)
    answer_must_contain: list[str] = field(default_factory=list)  # case-insensitive substrings
    answer_must_not_contain: list[str] = field(default_factory=list)  # case-insensitive substrings; PHI-safety lives here
    expect_escalation: bool | None = None  # None = not checked
    expect_verification_required: bool = False  # expects the reply to be gated, not to contain PHI
    notes: str = ""


@dataclass
class ScenarioTurn:
    """One simulated customer utterance. Scenarios operate at the
    transcript (text) level, not real audio -- the same text-in/text-out
    abstraction already used to test the conversation pipeline elsewhere
    in this project. STT/TTS quality is evaluated separately, once real
    Azure calls are unblocked (Priority 1)."""

    customer_utterance: str


@dataclass
class Scenario:
    id: str
    description: str
    category: ScenarioCategory
    turns: list[ScenarioTurn]
    expected: ExpectedBehavior
    # True ONLY for the small set in fixtures.py that exist to prove the
    # harness mechanics work. Never set True for a scenario meant to
    # represent real domain validation -- see report.py, which refuses to
    # summarize fixture and non-fixture results together.
    is_test_fixture: bool = False


@dataclass
class ObservedToolCall:
    name: str
    args: dict
    # The tool's raw return string (e.g. "[VERIFICATION REQUIRED] ..."),
    # distinct from the LLM's eventual spoken reply -- the LLM paraphrases
    # a gated tool result rather than repeating it verbatim, so gating
    # correctness has to be checked here, not against final_reply.
    output: str = ""


@dataclass
class ObservedBehavior:
    """What actually happened when a scenario was run, regardless of
    executor (real pipeline or fake)."""

    tool_calls: list[ObservedToolCall] = field(default_factory=list)
    final_reply: str = ""
    escalated: bool = False
    confidence_scores: list[float] = field(default_factory=list)
    latency_ms: float | None = None
    # None until Azure OpenAI's usage field is wired through chat_completion
    # (it currently isn't -- app/llm/client.py doesn't return token counts).
    # Left as a typed field rather than omitted, so cost reporting has
    # somewhere to plug in without a schema change once that's added.
    cost_usd: float | None = None
    technical_error: str | None = None
