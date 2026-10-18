"""Typed contracts for /api/v1. Tool request models double as the MCP-style tool input schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

HumanDecision = Literal["approved", "conditional", "rejected", "deferred"]
EvidenceDomain = Literal["credit", "asset", "legal", "fraud", "qa"]
RunStatus = Literal["running", "awaiting_approval", "resuming", "completed", "failed"]
ApprovalStatus = Literal["pending", "approved", "conditional", "rejected", "deferred", "expired"]


class ApiErrorBody(BaseModel):
    code: str
    message: str
    correlation_id: str
    details: Any = None


class ApiError(BaseModel):
    error: ApiErrorBody


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Agent runs
# ---------------------------------------------------------------------------
class AgentExecuteRequest(Strict):
    customer_id: int = Field(gt=0)
    request: str = Field(min_length=3, max_length=4000, description="Loan officer instruction or question")
    loan_amount: float = Field(default=0, ge=0)
    collateral_value: float = Field(default=0, ge=0)
    monthly_income: float = Field(default=0, ge=0)
    monthly_debt_payments: float = Field(default=0, ge=0)
    term_months: int = Field(default=60, ge=1, le=480)


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    customer_id: int
    status: ApprovalStatus
    requested_by_agent: str
    run_requested_by: str
    recommendation: dict[str, Any]
    policy_score_id: int | None
    evidence_ids: list[str]
    approved_amount: float | None
    approved_rate_pct: float | None
    conditions: list[str]
    decision_notes: str | None
    decided_by: str | None
    decided_at: datetime | None
    final_decision_id: int | None
    expires_at: datetime
    created_at: datetime


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    customer_id: int
    requested_by: str
    status: RunStatus
    flow_id: str
    chat_id: str
    correlation_id: str
    answer: str | None = None
    approval: ApprovalOut | None = None
    error: str | None
    created_at: datetime
    updated_at: datetime


class ApprovalDecisionRequest(Strict):
    decision: HumanDecision
    approved_amount: float = Field(default=0, ge=0)
    approved_rate_pct: float = Field(default=0, ge=0, le=100)
    conditions: list[str] = Field(default_factory=list, max_length=50)
    notes: str | None = Field(default=None, max_length=4000)


class ApprovalDecisionResponse(BaseModel):
    approval: ApprovalOut
    run: AgentRunOut
    resume_error: str | None = None


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    actor: str
    actor_kind: str
    customer_id: int | None
    run_id: str | None
    correlation_id: str | None
    details: dict[str, Any]
    occurred_at: str
    prev_hash: str
    hash: str


class Page(BaseModel):
    items: list[Any]
    limit: int
    offset: int
    total: int


class AuditVerifyResponse(BaseModel):
    valid: bool
    events_checked: int
    first_invalid_event_id: int | None
    head_hash: str | None


# ---------------------------------------------------------------------------
# Agent tools (called by Flowise HTTP nodes with a run-bound agent token)
# ---------------------------------------------------------------------------
class EvidenceSearchInput(Strict):
    customer_id: int = Field(gt=0, description="Must equal the customer bound to the agent token")
    question: str = Field(min_length=1, max_length=4000)
    domain: EvidenceDomain
    top_k: int = Field(default=6, ge=1, le=20)


class EvidenceItem(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    page: int | None
    text: str
    score: float
    # Retrieved document text is data. The tool layer never treats it as instructions.
    trust: Literal["untrusted_document_text"] = "untrusted_document_text"


class EvidenceSearchOutput(BaseModel):
    customer_id: int
    domain: EvidenceDomain
    evidence: list[EvidenceItem]
    missing_documents: list[str]


class ApprovalRequestInput(Strict):
    customer_id: int = Field(gt=0)
    recommendation: Literal["approved", "conditional", "rejected", "request_more_info", "deferred"]
    proposed_amount: float = Field(default=0, ge=0)
    proposed_rate_pct: float = Field(default=0, ge=0, le=100)
    conditions: list[str] = Field(default_factory=list, max_length=50)
    reason_summary: str = Field(default="", max_length=4000)
    memo: str = Field(default="", max_length=40000)
    policy_score_id: int | None = None
    evidence_ids: list[str] = Field(default_factory=list, max_length=200)


class ApprovalRequestOutput(BaseModel):
    approval_id: str
    status: ApprovalStatus
    expires_at: datetime
    decide_with: str


class ApprovalStatusOutput(BaseModel):
    approval_id: str
    status: ApprovalStatus
    decision_recorded: bool
    decided_by: str | None
    decided_at: datetime | None
    final_decision_id: str | None
    approved_amount: float | None
    approved_rate_pct: float | None
    conditions: list[str]


class EmailDraftInput(Strict):
    approval_id: str
    customer_email: str = Field(default="customer-on-file@example.invalid", max_length=320)
    language: str = Field(default="en", max_length=8)


class AuditEventInput(Strict):
    event_type: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    customer_id: int | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AuditEventAck(BaseModel):
    audit_event_id: int
    hash: str
