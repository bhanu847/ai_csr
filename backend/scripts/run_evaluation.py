"""CLI entry point for the evaluation framework.

Default mode (no args) runs the harness-proving fixtures through
FakeExecutor -- no Azure, no DB writes beyond what's already required by
the app being importable. This is NOT domain validation; see
app/evaluation/fixtures.py's module docstring.

Real-pipeline mode (--real --tenant-id ... --agent-id ...) drives fixtures
through RealPipelineExecutor against a live Azure OpenAI deployment.
CURRENTLY BLOCKED -- there is no Azure OpenAI credential configured in this
environment as of this script's authorship, so --real has never been run
successfully. It exists so this is a one-command operation the moment
AZURE_OPENAI_*/AZURE_SPEECH_* are set, not something to build later.

Usage:
    venv/Scripts/python.exe scripts/run_evaluation.py
    venv/Scripts/python.exe scripts/run_evaluation.py --json
    venv/Scripts/python.exe scripts/run_evaluation.py --real --tenant-id <uuid> --agent-id <uuid>
"""

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.evaluation.fixtures import FIXTURE_SCENARIOS, FakeExecutor  # noqa: E402
from app.evaluation.report import render_report, to_json  # noqa: E402
from app.evaluation.runner import RealPipelineExecutor, run_scenario  # noqa: E402
from app.evaluation.scoring import score_scenario  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--real", action="store_true", help="Use RealPipelineExecutor (needs Azure OpenAI configured)")
    parser.add_argument("--tenant-id", type=str, help="Required with --real")
    parser.add_argument("--agent-id", type=str, help="Required with --real")
    parser.add_argument("--json", action="store_true", help="Print structured JSON instead of the text report")
    args = parser.parse_args()

    if args.real:
        if not args.tenant_id or not args.agent_id:
            parser.error("--real requires --tenant-id and --agent-id")
        executor = RealPipelineExecutor(tenant_id=uuid.UUID(args.tenant_id), agent_id=uuid.UUID(args.agent_id))
        print(
            "WARNING: --real mode has not been verified end-to-end -- no Azure OpenAI credential exists "
            "in this environment as of this script's authorship. If this call fails, that is expected "
            "until AZURE_OPENAI_*/AZURE_SPEECH_* are configured.",
            file=sys.stderr,
        )
    else:
        executor = FakeExecutor()
        print(
            "Running HARNESS TEST FIXTURES only (FakeExecutor, no Azure/DB) -- "
            "this proves the harness works, it is not domain validation.",
            file=sys.stderr,
        )

    results = [score_scenario(s, run_scenario(s, executor)) for s in FIXTURE_SCENARIOS]

    if args.json:
        print(to_json(results))
    else:
        print(render_report(results))


if __name__ == "__main__":
    main()
