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


class IngestionStatus(BaseModel):
    parser: str = "pending"
    chunker: str = "pending"
    embeddings: str = "pending"
    postgresql: str = "pending"
    pgvector: str = "pending"


class DocumentUploadResponse(DocumentOut):
    document_id: str
    session_id: str | None = None
    ingestion_status: IngestionStatus = Field(default_factory=IngestionStatus)


class DocumentStatusResponse(BaseModel):
    document_id: str
    customer_id: str
    parser: str
    chunker: str
    embeddings: str
    postgresql: str
    pgvector: str
    chunks_count: int = 0
    embedding_model: str = "local-hash-embedding"
    indexed_at: datetime | None = None
    error: str | None = None


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
    service: str = "docfactor-banking-api"
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
    session_id: str | None = None
    policy_mode: str = "standard_credit_policy"
    loan_amount: float | None = 0
    collateral_value: float | None = 0
    monthly_income: float | None = 0
    monthly_debt_payments: float | None = None
    monthly_debt: float | None = None
    annual_interest_rate: float | None = None
    term_months: int | None = 60
    evidence: list[dict] = Field(default_factory=list)
    fraud_indicators: list[str] = Field(default_factory=list)
    missing_documents: list[str] = Field(default_factory=list)
    assessment_id: str | None = None


class LoanPolicyResponse(BaseModel):
    policy_score_id: int | None = None
    customer_id: str
    policy_mode: str = "standard_credit_policy"
    assessment_id: str | None = None
    dti: DTIResult
    ltv: LTVResult
    interest: InterestResult
    policy: PolicyDecisionResult
    fraud: FraudResult
    missing_documents: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    dti_ratio: float | None = None
    ltv_ratio: float | None = None
    interest_rate: float | None = None
    monthly_payment: float | None = None
    policy_breaches: list[str] = Field(default_factory=list)
    risk_level: str = "medium"
    recommendation: str = "review"
    human_review_required: bool = True
    explanation: list[str] = Field(default_factory=list)


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
    decision: Literal["approved", "rejected", "conditional", "deferred", "request_more_info"]
    approved_amount: float = 0
    approved_rate_pct: float = 0
    conditions: list[str] = Field(default_factory=list)
    decision_by: str | None = None
    decided_by: str | None = None
    decision_notes: str | None = None
    notes: str | None = None


class FinalDecisionResponse(BaseModel):
    decision_id: str
    status: str = "final_decision_recorded"
    note: str = "Final decision made by authorized credit officer / committee, not AI."


class CustomerDecisionEmailDraftRequest(BaseModel):
    customer_id: str
    customer_email: str = "customer@example.com"
    decision: Literal["approved", "rejected", "conditional", "deferred", "request_more_info"] = "conditional"
    approved_amount: float = 0
    approved_rate_pct: float = 0
    conditions: list[str] = Field(default_factory=list)
    reason_summary: str | None = None
    officer_name: str = "Credit Officer"
    decision_id: str | None = None
    language: str = "en"


class CustomerDecisionEmailDraftResponse(BaseModel):
    email_draft_id: str | None = None
    subject: str
    body: str
    send_allowed: bool = False
    requires_human_approval: bool = True
