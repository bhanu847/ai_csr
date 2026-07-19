import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.audit import logger as audit
from app.auth.dependencies import CurrentUser, get_db, require_role
from app.models.user import Role
from app.models.workflow import Workflow, WorkflowStep
from app.tools.schemas import TOOL_SCHEMAS

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


class WorkflowStepPayload(BaseModel):
    tool_name: str
    condition: str | None = Field(default=None, max_length=500)


class CreateWorkflowRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    trigger_description: str = Field(min_length=1, max_length=500)
    department: str | None = Field(default=None, max_length=50)
    is_active: bool = True
    steps: list[WorkflowStepPayload] = []


class UpdateWorkflowRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    trigger_description: str | None = Field(default=None, min_length=1, max_length=500)
    department: str | None = Field(default=None, max_length=50)
    is_active: bool | None = None
    steps: list[WorkflowStepPayload] | None = None


class WorkflowStepResponse(BaseModel):
    id: uuid.UUID
    step_order: int
    tool_name: str
    condition: str | None

    model_config = {"from_attributes": True}


class WorkflowResponse(BaseModel):
    id: uuid.UUID
    name: str
    trigger_description: str
    department: str | None
    is_active: bool
    created_at: datetime
    steps: list[WorkflowStepResponse]

    model_config = {"from_attributes": True}


def _apply_steps(workflow: Workflow, tenant_id: uuid.UUID, steps: list[WorkflowStepPayload]) -> None:
    workflow.steps.clear()  # cascade="all, delete-orphan" removes the old rows on flush
    for i, step in enumerate(steps, start=1):
        workflow.steps.append(
            WorkflowStep(tenant_id=tenant_id, step_order=i, tool_name=step.tool_name, condition=step.condition)
        )


@router.get("/available-tools", response_model=list[str])
def list_available_tools() -> list[str]:
    return [schema["function"]["name"] for schema in TOOL_SCHEMAS]


@router.get("", response_model=list[WorkflowResponse])
def list_workflows(db: Session = Depends(get_db)) -> list[Workflow]:
    return list(
        db.execute(select(Workflow).options(selectinload(Workflow.steps)).order_by(Workflow.created_at.desc()))
        .scalars()
    )


@router.post("", response_model=WorkflowResponse, status_code=201)
def create_workflow(
    body: CreateWorkflowRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.ADMIN, Role.AGENT_BUILDER)),
) -> Workflow:
    workflow = Workflow(
        tenant_id=current_user.tenant_id,
        name=body.name,
        trigger_description=body.trigger_description,
        department=body.department,
        is_active=body.is_active,
    )
    _apply_steps(workflow, current_user.tenant_id, body.steps)
    db.add(workflow)
    db.flush()
    audit.record(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="workflow.created",
        resource_type="workflow",
        resource_id=str(workflow.id),
    )
    return workflow


@router.get("/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(workflow_id: uuid.UUID, db: Session = Depends(get_db)) -> Workflow:
    workflow = db.execute(
        select(Workflow).options(selectinload(Workflow.steps)).where(Workflow.id == workflow_id)
    ).scalar_one_or_none()
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@router.patch("/{workflow_id}", response_model=WorkflowResponse)
def update_workflow(
    workflow_id: uuid.UUID,
    body: UpdateWorkflowRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.ADMIN, Role.AGENT_BUILDER)),
) -> Workflow:
    workflow = db.execute(
        select(Workflow).options(selectinload(Workflow.steps)).where(Workflow.id == workflow_id)
    ).scalar_one_or_none()
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if body.name is not None:
        workflow.name = body.name
    if body.trigger_description is not None:
        workflow.trigger_description = body.trigger_description
    if body.department is not None:
        workflow.department = body.department or None
    if body.is_active is not None:
        workflow.is_active = body.is_active
    if body.steps is not None:
        _apply_steps(workflow, current_user.tenant_id, body.steps)

    db.flush()
    audit.record(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="workflow.updated",
        resource_type="workflow",
        resource_id=str(workflow.id),
    )
    return workflow


@router.delete("/{workflow_id}", status_code=204)
def delete_workflow(
    workflow_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.ADMIN, Role.AGENT_BUILDER)),
) -> None:
    workflow = db.execute(select(Workflow).where(Workflow.id == workflow_id)).scalar_one_or_none()
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    db.delete(workflow)
    db.flush()
    audit.record(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="workflow.deleted",
        resource_type="workflow",
        resource_id=str(workflow_id),
    )
