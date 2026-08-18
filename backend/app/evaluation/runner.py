"""Executes a Scenario and produces an ObservedBehavior.

Two executors:
  - RealPipelineExecutor -- drives the scenario through the actual
    ConversationSession/run_turn/CallContext pipeline, exactly like a real
    call. Requires a working Azure OpenAI deployment. THIS IS CURRENTLY
    BLOCKED: no Azure credentials exist in this environment yet, so this
    executor has never successfully run end-to-end. It's written and ready
    for the moment that changes -- see README.md's Concurrency & scaling
    section and the project's Priority 1.
  - Any other callable matching the ConversationExecutor protocol -- tests
    use a small scripted fake (tests/evaluation/test_harness.py) so the
    runner/scoring/aggregation mechanics can be proven without Azure.

run_scenario() itself has no opinion about which executor it's given; it
only measures wall-clock time and converts an exception into a
technical_error rather than letting the whole evaluation run crash on one
bad scenario.
"""

import time
import uuid
from typing import Protocol

from app.evaluation.schema import ObservedBehavior, ObservedToolCall, Scenario


class ConversationExecutor(Protocol):
    def __call__(self, scenario: Scenario) -> ObservedBehavior: ...


class RealPipelineExecutor:
    """See module docstring -- BLOCKED on Azure credentials, never yet run
    against a live model. Reuses tool_execution_logs (the same persistence
    path a real call already writes to) to reconstruct which tools were
    called, rather than adding new instrumentation to app/conversation or
    app/tools for evaluation purposes."""

    def __init__(self, tenant_id: uuid.UUID, agent_id: uuid.UUID, customer_id: uuid.UUID | None = None) -> None:
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.customer_id = customer_id

    def __call__(self, scenario: Scenario) -> ObservedBehavior:
        from sqlalchemy import select

        from app.conversation.agent import run_turn
        from app.conversation.orchestrator import ConversationSession
        from app.db.session import tenant_session
        from app.models.agent import Agent
        from app.models.call import Call, CallStatus
        from app.models.tool_execution_log import ToolExecutionLog
        from app.tools.context import CallContext

        started = time.perf_counter()
        try:
            with tenant_session(self.tenant_id) as db:
                agent = db.execute(select(Agent).where(Agent.id == self.agent_id)).scalar_one()

                call = Call(
                    tenant_id=self.tenant_id,
                    agent_id=self.agent_id,
                    customer_id=self.customer_id,
                    twilio_call_sid=f"EVAL-{scenario.id}-{uuid.uuid4().hex[:8]}",
                    from_number="+10000000000",
                    to_number="+19999999999",
                    status=CallStatus.IN_PROGRESS,
                )
                db.add(call)
                db.flush()
                call_id = call.id

                session = ConversationSession(agent_name=agent.name, persona=agent.persona)
                session.department = (agent.department or "general").lower()

                final_reply = ""
                confidences: list[float] = []
                for turn in scenario.turns:
                    session.add_user_message(turn.customer_utterance)
                    ctx = CallContext(
                        db=db,
                        tenant_id=self.tenant_id,
                        agent_id=self.agent_id,
                        call_id=call_id,
                        customer_id=self.customer_id,
                        department=session.department,
                        verified_member_id=session.verified_member_id,
                    )
                    final_reply = run_turn(session, ctx)
                    session.verified_member_id = ctx.verified_member_id
                    if ctx.last_confidence is not None:
                        confidences.append(ctx.last_confidence)

                logs = db.execute(
                    select(ToolExecutionLog).where(ToolExecutionLog.call_id == call_id)
                ).scalars().all()
                tool_calls = [
                    ObservedToolCall(name=log.tool_name, args=log.input or {}, output=log.output) for log in logs
                ]

            return ObservedBehavior(
                tool_calls=tool_calls,
                final_reply=final_reply,
                escalated=any(c.name == "escalate_to_human" for c in tool_calls),
                confidence_scores=confidences,
                latency_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:  # noqa: BLE001 -- deliberately broad: one bad scenario must not crash the run
            return ObservedBehavior(
                technical_error=f"{type(exc).__name__}: {exc}",
                latency_ms=(time.perf_counter() - started) * 1000,
            )


def run_scenario(scenario: Scenario, executor: ConversationExecutor) -> ObservedBehavior:
    try:
        return executor(scenario)
    except Exception as exc:  # noqa: BLE001 -- see RealPipelineExecutor's own catch; this is the belt-and-suspenders
        return ObservedBehavior(technical_error=f"{type(exc).__name__}: {exc}")
