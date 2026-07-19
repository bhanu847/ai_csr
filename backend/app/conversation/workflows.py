import uuid

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.workflow import Workflow


def get_active_workflows_context(db: Session, tenant_id: uuid.UUID, department: str) -> str | None:
    """Active workflows that apply to this department (plus tenant-wide
    ones with no department set), formatted as an explicit procedure list
    for the system prompt. Returns None if there are none — same "omit the
    section entirely" pattern as customer memory."""
    department = department.lower()
    workflows = (
        db.execute(
            select(Workflow)
            .options(selectinload(Workflow.steps))
            .where(
                Workflow.tenant_id == tenant_id,
                Workflow.is_active.is_(True),
                or_(Workflow.department.is_(None), Workflow.department == department),
            )
        )
        .scalars()
        .all()
    )
    if not workflows:
        return None

    blocks = []
    for wf in workflows:
        if not wf.steps:
            continue
        step_lines = "\n".join(
            f"  {i}. {step.tool_name}" + (f" — {step.condition}" if step.condition else "")
            for i, step in enumerate(wf.steps, start=1)
        )
        blocks.append(f'"{wf.name}" — when: {wf.trigger_description}\n{step_lines}')

    return "\n\n".join(blocks) if blocks else None
