import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import logger as audit
from app.auth.dependencies import CurrentUser, get_db, require_role
from app.models.agent import Agent
from app.models.appointment import Appointment
from app.models.user import Role

router = APIRouter(prefix="/api/agents", tags=["agents"])


class CreateAgentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    persona: str = Field(default="", max_length=2000)
    voice: str = Field(default="en-IN-NeerjaNeural", max_length=100)
    department: str = Field(default="general", max_length=50)


class UpdateAgentRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    persona: str | None = Field(default=None, max_length=2000)
    voice: str | None = Field(default=None, max_length=100)
    department: str | None = Field(default=None, max_length=50)
    is_default: bool | None = None


class AgentResponse(BaseModel):
    id: uuid.UUID
    name: str
    persona: str
    voice: str
    department: str
    is_default: bool

    model_config = {"from_attributes": True}


@router.post("", response_model=AgentResponse, status_code=201)
def create_agent(
    body: CreateAgentRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.ADMIN, Role.AGENT_BUILDER)),
) -> Agent:
    is_first_agent = (
        db.execute(select(Agent).where(Agent.tenant_id == current_user.tenant_id)).first() is None
    )
    agent = Agent(
        tenant_id=current_user.tenant_id,
        name=body.name,
        persona=body.persona,
        voice=body.voice,
        department=body.department,
        is_default=is_first_agent,
    )
    db.add(agent)
    db.flush()
    audit.record(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="agent.created",
        resource_type="agent",
        resource_id=str(agent.id),
    )
    return agent


@router.get("", response_model=list[AgentResponse])
def list_agents(db: Session = Depends(get_db)) -> list[Agent]:
    return list(db.execute(select(Agent)).scalars())


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(agent_id: uuid.UUID, db: Session = Depends(get_db)) -> Agent:
    agent = db.execute(select(Agent).where(Agent.id == agent_id)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.patch("/{agent_id}", response_model=AgentResponse)
def update_agent(
    agent_id: uuid.UUID,
    body: UpdateAgentRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.ADMIN, Role.AGENT_BUILDER)),
) -> Agent:
    agent = db.execute(select(Agent).where(Agent.id == agent_id)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    if body.name is not None:
        agent.name = body.name
    if body.persona is not None:
        agent.persona = body.persona
    if body.voice is not None:
        agent.voice = body.voice
    if body.department is not None:
        agent.department = body.department
    if body.is_default is True:
        for other in db.execute(
            select(Agent).where(Agent.tenant_id == current_user.tenant_id, Agent.id != agent.id)
        ).scalars():
            other.is_default = False
        agent.is_default = True

    db.flush()
    audit.record(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="agent.updated",
        resource_type="agent",
        resource_id=str(agent.id),
    )
    return agent


@router.delete("/{agent_id}", status_code=204)
def delete_agent(
    agent_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(Role.ADMIN, Role.AGENT_BUILDER)),
) -> None:
    agent = db.execute(select(Agent).where(Agent.id == agent_id)).scalar_one_or_none()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent.is_default:
        raise HTTPException(
            status_code=409, detail="Cannot delete the default agent — set another agent as default first"
        )

    has_appointments = (
        db.execute(select(Appointment.id).where(Appointment.agent_id == agent_id).limit(1)).first() is not None
    )
    if has_appointments:
        raise HTTPException(
            status_code=409, detail="Cannot delete an agent with booked appointments"
        )

    db.delete(agent)
    db.flush()
    audit.record(
        db,
        tenant_id=current_user.tenant_id,
        actor_user_id=current_user.id,
        action="agent.deleted",
        resource_type="agent",
        resource_id=str(agent_id),
    )
