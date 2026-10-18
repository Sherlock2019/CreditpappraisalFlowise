from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    customer_type: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(Text)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False, default="demo", server_default="demo", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    documents: Mapped[list["Document"]] = relationship(back_populates="customer")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    document_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str | None] = mapped_column(Text, default="uploaded")
    source_type: Mapped[str | None] = mapped_column(Text, default="manual_upload")
    source_uri: Mapped[str | None] = mapped_column(Text)
    external_document_id: Mapped[str | None] = mapped_column(Text)
    source_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    customer: Mapped[Customer] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(back_populates="document")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_metadata: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(1536))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="chunks")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CreditAssessment(Base):
    __tablename__ = "credit_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    risk_level: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int | None] = mapped_column(Integer)
    summary: Mapped[str | None] = mapped_column(Text)
    strengths: Mapped[str | None] = mapped_column(Text)
    weaknesses: Mapped[str | None] = mapped_column(Text)
    missing_documents: Mapped[str | None] = mapped_column(Text)
    human_review_required: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AssetAppraisal(Base):
    __tablename__ = "asset_appraisals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    asset_name: Mapped[str] = mapped_column(Text, nullable=False)
    asset_class: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    appraised_value: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    valuation_method: Mapped[str] = mapped_column(Text, default="market_comparison")
    haircut_pct: Mapped[float] = mapped_column(Float, default=20.0)
    collateral_value: Mapped[float] = mapped_column(Float, nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, default=75)
    status: Mapped[str] = mapped_column(Text, default="draft")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"))
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class LoanPolicyScore(Base):
    __tablename__ = "loan_policy_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[str] = mapped_column(Text, nullable=False)
    assessment_id: Mapped[str | None] = mapped_column(Text)
    dti_pct: Mapped[float | None] = mapped_column(Float)
    dti_band: Mapped[str | None] = mapped_column(Text)
    ltv_pct: Mapped[float | None] = mapped_column(Float)
    ltv_band: Mapped[str | None] = mapped_column(Text)
    base_rate_pct: Mapped[float | None] = mapped_column(Float)
    risk_spread_pct: Mapped[float | None] = mapped_column(Float)
    estimated_annual_rate_pct: Mapped[float | None] = mapped_column(Float)
    estimated_monthly_payment: Mapped[float | None] = mapped_column(Float)
    recommendation: Mapped[str | None] = mapped_column(Text)
    committee_required: Mapped[bool] = mapped_column(Boolean, default=False)
    fraud_severity: Mapped[int] = mapped_column(Integer, default=0)
    reason_codes: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ApprovalCommitteeCase(Base):
    __tablename__ = "approval_committee_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[str] = mapped_column(Text, nullable=False)
    assessment_id: Mapped[str | None] = mapped_column(Text)
    policy_score_id: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, default="submitted_to_committee")
    submitted_by: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FinalDecision(Base):
    __tablename__ = "final_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    committee_case_id: Mapped[str | None] = mapped_column(Text)
    customer_id: Mapped[str] = mapped_column(Text, nullable=False)
    decision: Mapped[str] = mapped_column(Text, nullable=False)
    approved_amount: Mapped[float | None] = mapped_column(Float)
    approved_rate_pct: Mapped[float | None] = mapped_column(Float)
    conditions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    decision_by: Mapped[str] = mapped_column(Text, nullable=False)
    decision_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DecisionEmailDraft(Base):
    __tablename__ = "decision_email_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[str] = mapped_column(Text, nullable=False)
    decision_id: Mapped[str | None] = mapped_column(Text)
    customer_email: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    send_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_human_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# JSONB on PostgreSQL, plain JSON elsewhere (the unit tests run on SQLite).
PortableJSON = JSON().with_variant(JSONB(), "postgresql")


class AgentRun(Base):
    """One governed execution of the credit appraisal Agentflow. FastAPI owns this state; Flowise owns the reasoning."""

    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    requested_by: Mapped[str] = mapped_column(Text, nullable=False)
    # running -> awaiting_approval -> resuming -> completed | failed
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    flow_id: Mapped[str] = mapped_column(Text, nullable=False)
    chat_id: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[str] = mapped_column(Text, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    request: Mapped[dict] = mapped_column(PortableJSON, nullable=False, default=dict)
    result: Mapped[dict] = mapped_column(PortableJSON, nullable=False, default=dict)
    human_input_node_id: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("uq_agent_runs_tenant_idempotency", "tenant_id", "idempotency_key", unique=True),)


class Approval(Base):
    """Human approval gate. Only an authenticated human with approval:decide can move it out of pending."""

    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), nullable=False)
    # pending -> approved | conditional | rejected | deferred | expired
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    requested_by_agent: Mapped[str] = mapped_column(Text, nullable=False)
    run_requested_by: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[dict] = mapped_column(PortableJSON, nullable=False, default=dict)
    policy_score_id: Mapped[int | None] = mapped_column(Integer)
    evidence_ids: Mapped[list] = mapped_column(PortableJSON, nullable=False, default=list)
    approved_amount: Mapped[float | None] = mapped_column(Float)
    approved_rate_pct: Mapped[float | None] = mapped_column(Float)
    conditions: Mapped[list] = mapped_column(PortableJSON, nullable=False, default=list)
    decision_notes: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    final_decision_id: Mapped[int | None] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditEvent(Base):
    """Tamper-evident audit trail: each row hashes the previous row of the same tenant."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    actor_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(Integer)
    run_id: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(PortableJSON, nullable=False, default=dict)
    occurred_at: Mapped[str] = mapped_column(Text, nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)

    __table_args__ = (Index("ix_audit_events_tenant_id_id", "tenant_id", "id"),)
