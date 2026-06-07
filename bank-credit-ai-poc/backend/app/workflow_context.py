from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app import models


FLOWISE_WORKFLOW_DEFAULTS: dict[str, Any] = {
    "loan_amount": "",
    "collateral_value": "",
    "monthly_income": "",
    "monthly_debt_payments": "",
    "term_months": "",
    "fraud_indicators": [],
    "missing_documents": [],
    "policy_score_id": "",
    "dti_pct": "",
    "dti_band": "",
    "ltv_pct": "",
    "ltv_band": "",
    "estimated_annual_rate_pct": "",
    "estimated_monthly_payment": "",
    "policy_recommendation": "",
    "committee_required": "",
    "reason_codes": [],
    "committee_case_id": "",
    "committee_status": "",
    "decision_id": "",
    "decision": "",
    "approved_amount": "",
    "approved_rate_pct": "",
    "conditions": [],
    "customer_email": "",
    "email_draft_id": "",
    "email_subject": "",
    "customer_email_draft": "",
}


def _value(value: Any) -> Any:
    if value is None:
        return ""
    return value


def _serializable_context(context: dict[str, Any]) -> dict[str, Any]:
    serializable: dict[str, Any] = {}
    for key, value in context.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            serializable[key] = _value(value)
        elif isinstance(value, (list, dict)):
            serializable[key] = value
        else:
            serializable[key] = str(value)
    return serializable


def build_flowise_workflow_context(
    db: Session,
    customer_id: int,
    request_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the workflow state that Flowise receives as runtime variables."""
    customer_key = str(customer_id)
    context = dict(FLOWISE_WORKFLOW_DEFAULTS)

    policy = (
        db.query(models.LoanPolicyScore)
        .filter(models.LoanPolicyScore.customer_id == customer_key)
        .order_by(models.LoanPolicyScore.id.desc())
        .first()
    )
    if policy:
        context.update(
            {
                "policy_score_id": policy.id,
                "dti_pct": policy.dti_pct,
                "dti_band": policy.dti_band,
                "ltv_pct": policy.ltv_pct,
                "ltv_band": policy.ltv_band,
                "estimated_annual_rate_pct": policy.estimated_annual_rate_pct,
                "estimated_monthly_payment": policy.estimated_monthly_payment,
                "policy_recommendation": policy.recommendation,
                "committee_required": policy.committee_required,
                "reason_codes": policy.reason_codes or [],
            }
        )

    committee = (
        db.query(models.ApprovalCommitteeCase)
        .filter(models.ApprovalCommitteeCase.customer_id == customer_key)
        .order_by(models.ApprovalCommitteeCase.id.desc())
        .first()
    )
    if committee:
        context.update(
            {
                "committee_case_id": f"COM-{committee.id}",
                "committee_status": committee.status,
            }
        )

    decision = (
        db.query(models.FinalDecision)
        .filter(models.FinalDecision.customer_id == customer_key)
        .order_by(models.FinalDecision.id.desc())
        .first()
    )
    if decision:
        context.update(
            {
                "decision_id": f"DEC-{decision.id}",
                "decision": decision.decision,
                "approved_amount": decision.approved_amount,
                "approved_rate_pct": decision.approved_rate_pct,
                "conditions": decision.conditions or [],
            }
        )

    email = (
        db.query(models.DecisionEmailDraft)
        .filter(models.DecisionEmailDraft.customer_id == customer_key)
        .order_by(models.DecisionEmailDraft.id.desc())
        .first()
    )
    if email:
        context.update(
            {
                "email_draft_id": f"EMAIL-{email.id}",
                "customer_email": email.customer_email,
                "email_subject": email.subject,
                "customer_email_draft": email.body,
            }
        )

    if request_context:
        for key, value in request_context.items():
            if value not in (None, ""):
                context[key] = value

    context = _serializable_context(context)
    context["workflow_state_json"] = json.dumps(context, ensure_ascii=True, sort_keys=True)
    return context
