from datetime import datetime

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CustomerCreate(BaseModel):
    name: str
    customer_type: str
    industry: str | None = None
    country: str | None = None


class CustomerOut(CustomerCreate):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentOut(BaseModel):
    id: int
    customer_id: int
    filename: str
    document_type: str | None = None
    status: str | None = None
    source_type: str | None = None
    source_uri: str | None = None
    external_document_id: str | None = None
    source_metadata: dict = Field(default_factory=dict)
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class IngestResponse(BaseModel):
    document_id: int
    status: str
    chunks_created: int


class Citation(BaseModel):
    filename: str
    document_type: str | None = None
    page_number: int | None = None
    chunk_index: int | None = None
    score: float | None = None


class RetrievedChunk(Citation):
    chunk_text: str


class ChatRequest(BaseModel):
    customer_id: int | None = None
    message: str
    session_id: int | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    temperature: float = 0.2
    max_tokens: int = 1200
    custom_public_api_base_url: str | None = None
    custom_public_api_key: str | None = None
    custom_public_api_model: str | None = None
    workflow_context: dict = Field(default_factory=dict)


class CreditAssessmentRequest(BaseModel):
    llm_provider: str | None = None
    llm_model: str | None = None
    temperature: float = 0.2
    max_tokens: int = 1500
    custom_public_api_base_url: str | None = None
    custom_public_api_key: str | None = None
    custom_public_api_model: str | None = None
    workflow_context: dict = Field(default_factory=dict)


class ChatResponse(BaseModel):
    session_id: int
    answer: str
    citations: list[Citation]
    retrieved_chunks: list[RetrievedChunk]
    llm_provider_used: str
    llm_model_used: str
    flowise_used: bool
    fallback_used: bool


class CreditAssessmentResponse(BaseModel):
    customer_id: int
    answer: str
    heuristic_score: int
    heuristic_risk_level: str
    matched_positive_signals: list[str]
    matched_negative_signals: list[str]
    citations: list[Citation]
    retrieved_chunks: list[RetrievedChunk]
    llm_provider_used: str
    llm_model_used: str
    flowise_used: bool
    fallback_used: bool


class AssetAppraisalCreate(BaseModel):
    customer_id: int
    asset_name: str
    asset_class: Literal["real_estate", "securities", "equipment", "inventory", "other"] = "real_estate"
    description: str | None = None
    appraised_value: float
    currency: str = "USD"
    valuation_method: str = "market_comparison"
    haircut_pct: float = 20.0
    confidence_score: int = 75
    status: str = "draft"
    notes: str | None = None


class AssetAppraisalOut(AssetAppraisalCreate):
    id: int
    collateral_value: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssetAppraisalSummary(BaseModel):
    customer_id: int
    total_appraised_value: float
    total_collateral_value: float
    appraisal_count: int
    by_class: dict[str, float]


class ProviderOption(BaseModel):
    label: str
    value: str
    default_model: str


class ConnectorOption(BaseModel):
    label: str
    value: str
    status: str
    description: str


class ConnectorOptionsResponse(BaseModel):
    connectors: list[ConnectorOption]


class ConnectorTestRequest(BaseModel):
    source_type: str
    config: dict = Field(default_factory=dict)


class ConnectorTestResponse(BaseModel):
    source_type: str
    success: bool
    message: str
    details: dict = Field(default_factory=dict)


class ConnectorListDocumentsRequest(BaseModel):
    source_type: str
    customer_id: int | None = None
    prefix: str | None = None
    folder_path: str | None = None
    config: dict = Field(default_factory=dict)


class ExternalDocumentInfo(BaseModel):
    external_document_id: str
    filename: str
    source_uri: str
    size_bytes: int | None = None
    last_modified: str | None = None
    content_type: str | None = None
    metadata: dict = Field(default_factory=dict)


class ConnectorListDocumentsResponse(BaseModel):
    source_type: str
    documents: list[ExternalDocumentInfo]
    message: str


class ConnectorIngestRequest(BaseModel):
    source_type: str
    customer_id: int
    external_document_id: str | None = None
    source_uri: str | None = None
    filename: str | None = None
    config: dict = Field(default_factory=dict)


class ConnectorIngestResponse(BaseModel):
    source_type: str
    customer_id: int
    document_id: int | None = None
    filename: str | None = None
    status: str
    message: str


class HealthResponse(BaseModel):
    status: str = Field(default="ok")
    service: str = "docfactor-api"
    flowise_configured: bool = False
    flowise_base_url: str | None = None


class DTIResult(BaseModel):
    value_pct: float | None
    band: str
    assessment: str


class LTVResult(BaseModel):
    value_pct: float | None
    band: str
    assessment: str


class InterestResult(BaseModel):
    base_rate_pct: float
    risk_spread_pct: float
    estimated_annual_rate_pct: float
    estimated_monthly_payment: float


class PolicyDecisionResult(BaseModel):
    recommendation: str
    committee_required: bool
    final_decision_allowed: bool = False
    human_review_required: bool = True
    reason_codes: list[str] = Field(default_factory=list)


class FraudResult(BaseModel):
    indicators: list[str] = Field(default_factory=list)
    severity: int = 0


class LoanPolicyRequest(BaseModel):
    customer_id: str
    loan_amount: float
    collateral_value: float
    monthly_income: float
    monthly_debt_payments: float
    term_months: int = 60
    fraud_indicators: list[str] = Field(default_factory=list)
    missing_documents: list[str] = Field(default_factory=list)
    assessment_id: str | None = None


class LoanPolicyResponse(BaseModel):
    policy_score_id: int | None = None
    customer_id: str
    assessment_id: str | None = None
    dti: DTIResult
    ltv: LTVResult
    interest: InterestResult
    policy: PolicyDecisionResult
    fraud: FraudResult
    missing_documents: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)


class ApprovalCommitteeSubmitRequest(BaseModel):
    customer_id: str
    assessment_id: str | None = None
    policy_score: dict = Field(default_factory=dict)
    submitted_by: str
    notes: str | None = None


class ApprovalCommitteeSubmitResponse(BaseModel):
    committee_case_id: str
    status: str = "submitted_to_committee"
    next_step: str = "Final Decision"


class FinalDecisionRequest(BaseModel):
    committee_case_id: str | None = None
    customer_id: str
    decision: Literal["approved", "rejected", "conditional", "deferred"]
    approved_amount: float = 0
    approved_rate_pct: float = 0
    conditions: list[str] = Field(default_factory=list)
    decision_by: str
    decision_notes: str | None = None


class FinalDecisionResponse(BaseModel):
    decision_id: str
    status: str = "final_decision_recorded"
    note: str = "Final decision made by authorized credit officer / committee, not AI."


class CustomerDecisionEmailDraftRequest(BaseModel):
    customer_id: str
    customer_email: str
    decision: Literal["approved", "rejected", "conditional", "deferred"]
    approved_amount: float = 0
    approved_rate_pct: float = 0
    conditions: list[str] = Field(default_factory=list)
    reason_summary: str | None = None
    officer_name: str
    decision_id: str | None = None


class CustomerDecisionEmailDraftResponse(BaseModel):
    email_draft_id: str | None = None
    subject: str
    body: str
    send_allowed: bool = False
    requires_human_approval: bool = True
