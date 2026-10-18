from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from app.auth.dependencies import require_permission
from app.auth.principal import Principal
from app.database import get_db
from app.models import AgentRun
from app.schemas_v1 import AgentExecuteRequest, AgentRunOut, ApiError, ApprovalOut
from app.services.agent_runtime import AgentflowClient, get_agentflow_client, pending_approval, run_in_tenant, start_run

router = APIRouter(prefix="/api/v1/agents", tags=["v1 agents"], responses={401: {"model": ApiError}, 403: {"model": ApiError}, 404: {"model": ApiError}})


def run_out(db: Session, run: AgentRun) -> AgentRunOut:
    approval = pending_approval(db, run.id)
    out = AgentRunOut.model_validate(run)
    out.answer = (run.result or {}).get("answer") or None
    out.approval = ApprovalOut.model_validate(approval) if approval else None
    return out


@router.post("/execute", response_model=AgentRunOut, status_code=201, summary="Run the credit appraisal Agentflow for one customer")
def execute_agent(
    payload: AgentExecuteRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128),
    principal: Principal = Depends(require_permission("agent:execute")),
    db: Session = Depends(get_db),
    client: AgentflowClient = Depends(get_agentflow_client),
) -> AgentRunOut:
    """Starts a governed run. If the flow reaches the human approval gate the run is returned with
    status `awaiting_approval` and a pending approval; decide it with `POST /api/v1/approvals/{id}/decision`."""
    return run_out(db, start_run(db, principal, payload, idempotency_key, client))


@router.get("/runs/{run_id}", response_model=AgentRunOut)
def get_run(run_id: str, principal: Principal = Depends(require_permission("agent_run:read")), db: Session = Depends(get_db)) -> AgentRunOut:
    return run_out(db, run_in_tenant(db, run_id, principal.tenant_id))
