from __future__ import annotations

from pydantic import BaseModel, Field


class FlowiseRuntimeVars(BaseModel):
    customer_id: str | None = None
    session_id: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    temperature: float = 0.2
    max_tokens: int = 1200
    retrieved_context: str = ""
    citations: list[dict] = Field(default_factory=list)
    heuristic_score: int | None = None
    risk_signals: list[str] = Field(default_factory=list)
    loan_amount: float | None = None
    collateral_value: float | None = None
    monthly_income: float | None = None
    monthly_debt_payments: float | None = None
    term_months: int = 60
    dti_pct: float | None = None
    dti_band: str | None = None
    ltv_pct: float | None = None
    ltv_band: str | None = None
    estimated_annual_rate_pct: float | None = None
    estimated_monthly_payment: float | None = None
    policy_recommendation: str | None = None
    committee_required: bool | None = None
    reason_codes: list[str] = Field(default_factory=list)


class FlowisePredictionRequest(BaseModel):
    question: str
    vars: FlowiseRuntimeVars = Field(default_factory=FlowiseRuntimeVars)


class FlowisePredictionResponse(BaseModel):
    answer: str = ""
    raw_response: dict = Field(default_factory=dict)
    flowise_used: bool = False
    fallback_used: bool = False
    error_summary: str | None = None
    provider_metadata: dict = Field(default_factory=dict)
