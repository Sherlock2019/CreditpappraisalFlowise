import json
from typing import Any

from app.config import get_settings
from app.flowise.client import FlowiseClient
from app.flowise.schemas import FlowisePredictionRequest, FlowiseRuntimeVars
from app.workflow_context import FLOWISE_WORKFLOW_DEFAULTS


def _flowise_var(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True, sort_keys=True)
    return str(value)


def _optional_bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _optional_list(value: Any) -> list:
    if value in (None, ""):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else [value]
        except json.JSONDecodeError:
            return [value]
    return [value]


def _build_flowise_question(
    question: str,
    customer_id: int,
    context: str,
    runtime_vars: dict[str, Any],
) -> str:
    workflow_state = runtime_vars.get("workflow_state_json")
    if not workflow_state:
        workflow_state = json.dumps(runtime_vars, ensure_ascii=True, sort_keys=True)
    return f"""
Original user question:
{question}

Customer ID:
{customer_id}

Retrieved customer and policy context from FastAPI RAG:
{context or "No relevant context was retrieved."}

Live backend workflow state:
{workflow_state}

Key policy values:
- Loan amount: {runtime_vars.get("loan_amount") or "not supplied"}
- Collateral value: {runtime_vars.get("collateral_value") or "not supplied"}
- Monthly income: {runtime_vars.get("monthly_income") or "not supplied"}
- Monthly debt payments: {runtime_vars.get("monthly_debt_payments") or "not supplied"}
- DTI: {runtime_vars.get("dti_pct") or "not calculated"}% ({runtime_vars.get("dti_band") or "unknown"})
- LTV: {runtime_vars.get("ltv_pct") or "not calculated"}% ({runtime_vars.get("ltv_band") or "unknown"})
- Estimated annual rate: {runtime_vars.get("estimated_annual_rate_pct") or "not calculated"}%
- Estimated monthly payment: {runtime_vars.get("estimated_monthly_payment") or "not calculated"}
- Policy recommendation: {runtime_vars.get("policy_recommendation") or "not calculated"}
- Committee required: {runtime_vars.get("committee_required") or "unknown"}
- Committee case ID: {runtime_vars.get("committee_case_id") or "none"}
- Committee status: {runtime_vars.get("committee_status") or "none"}
- Final decision ID: {runtime_vars.get("decision_id") or "none"}
- Final decision: {runtime_vars.get("decision") or "none supplied"}
- Email draft ID: {runtime_vars.get("email_draft_id") or "none"}

Answer the original user question using only the retrieved context and workflow state above.
""".strip()


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def call_flowise_chat(
    question: str,
    customer_id: int,
    context: str,
    llm_provider: str,
    temperature: float,
    max_tokens: int,
    custom_public_api_model: str | None = None,
    llm_model: str | None = None,
    workflow_context: dict[str, Any] | None = None,
) -> dict[str, str]:
    settings = get_settings()
    if not settings.flowise_chatflow_id:
        raise RuntimeError("FLOWISE_CHATFLOW_ID is not configured")
    runtime_vars: dict[str, Any] = {
        **FLOWISE_WORKFLOW_DEFAULTS,
        **(workflow_context or {}),
        "customer_id": str(customer_id),
        "context": context,
        "llm_provider": llm_provider,
        "llm_model": llm_model or custom_public_api_model or "",
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    runtime_vars.setdefault("workflow_state_json", json.dumps(workflow_context or {}, ensure_ascii=True, sort_keys=True))

    request = FlowisePredictionRequest(
        question=_build_flowise_question(question, customer_id, context, runtime_vars),
        vars=FlowiseRuntimeVars(
            customer_id=str(customer_id),
            llm_provider=llm_provider,
            llm_model=llm_model or custom_public_api_model or None,
            temperature=temperature,
            max_tokens=max_tokens,
            retrieved_context=context,
            loan_amount=_optional_float(runtime_vars.get("loan_amount")),
            collateral_value=_optional_float(runtime_vars.get("collateral_value")),
            monthly_income=_optional_float(runtime_vars.get("monthly_income")),
            monthly_debt_payments=_optional_float(runtime_vars.get("monthly_debt_payments")),
            term_months=_optional_int(runtime_vars.get("term_months")) or 60,
            dti_pct=_optional_float(runtime_vars.get("dti_pct")),
            dti_band=runtime_vars.get("dti_band") or None,
            ltv_pct=_optional_float(runtime_vars.get("ltv_pct")),
            ltv_band=runtime_vars.get("ltv_band") or None,
            estimated_annual_rate_pct=_optional_float(runtime_vars.get("estimated_annual_rate_pct")),
            estimated_monthly_payment=_optional_float(runtime_vars.get("estimated_monthly_payment")),
            policy_recommendation=runtime_vars.get("policy_recommendation") or None,
            committee_required=_optional_bool(runtime_vars.get("committee_required")),
            reason_codes=_optional_list(runtime_vars.get("reason_codes")),
        ),
    )
    client = FlowiseClient(
        base_url=settings.flowise_base_url or settings.flowise_api_url,
        api_key=settings.flowise_api_key,
        chatflow_id=settings.flowise_chatflow_id,
    )
    prediction = await client.predict(request)
    if prediction.fallback_used:
        raise RuntimeError(prediction.error_summary or "Flowise prediction failed")
    return {
        "text": prediction.answer,
        "provider": llm_provider,
        "model": llm_model or custom_public_api_model or "",
    }
