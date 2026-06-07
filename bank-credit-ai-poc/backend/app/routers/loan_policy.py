from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import log_event
from app.database import get_db
from app.flowise_compat import ensure_customer
from app.policy.loan_policy import score_loan_policy

router = APIRouter(tags=["loan policy"])


def _audit_customer_id(customer_id: str) -> int | None:
    try:
        return int(customer_id)
    except (TypeError, ValueError):
        return None


def _case_id(raw_id: int) -> str:
    return f"COM-{raw_id}"


def _decision_id(raw_id: int) -> str:
    return f"DEC-{raw_id}"


def _email_id(raw_id: int) -> str:
    return f"EMAIL-{raw_id}"


def _parse_prefixed_id(value: str | None, prefix: str) -> int | None:
    if not value:
        return None
    text = str(value).strip()
    if text.upper().startswith(f"{prefix}-"):
        text = text.split("-", 1)[1]
    try:
        return int(text)
    except ValueError:
        return None


@router.post("/loan-policy/score", response_model=schemas.LoanPolicyResponse)
def calculate_policy_score(
    payload: schemas.LoanPolicyRequest,
    db: Session = Depends(get_db),
) -> schemas.LoanPolicyResponse:
    customer = ensure_customer(db, payload.customer_id)
    normalized_payload = payload.model_dump()
    if normalized_payload.get("monthly_debt_payments") is None:
        normalized_payload["monthly_debt_payments"] = normalized_payload.get("monthly_debt") or 0
    normalized_payload["customer_id"] = str(payload.customer_id)
    result = score_loan_policy(normalized_payload)
    record = models.LoanPolicyScore(
        customer_id=result["customer_id"],
        assessment_id=result.get("assessment_id"),
        dti_pct=result["dti"]["value_pct"],
        dti_band=result["dti"]["band"],
        ltv_pct=result["ltv"]["value_pct"],
        ltv_band=result["ltv"]["band"],
        base_rate_pct=result["interest"]["base_rate_pct"],
        risk_spread_pct=result["interest"]["risk_spread_pct"],
        estimated_annual_rate_pct=result["interest"]["estimated_annual_rate_pct"],
        estimated_monthly_payment=result["interest"]["estimated_monthly_payment"],
        recommendation=result["policy"]["recommendation"],
        committee_required=result["policy"]["committee_required"],
        fraud_severity=result["fraud"]["severity"],
        reason_codes=result["policy"]["reason_codes"],
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    result["policy_score_id"] = record.id
    result["policy_mode"] = payload.policy_mode
    dti_pct = result["dti"]["value_pct"]
    ltv_pct = result["ltv"]["value_pct"]
    flat_dti = round(dti_pct / 100, 6) if dti_pct is not None else None
    flat_ltv = round(ltv_pct / 100, 6) if ltv_pct is not None else None
    policy_breaches = list(result["policy"].get("reason_codes") or [])
    if dti_pct is None or ltv_pct is None:
        risk_level = "high"
        recommendation = "request_more_info"
    elif dti_pct <= 35 and ltv_pct <= 70 and not policy_breaches:
        risk_level = "low"
        recommendation = "approve_candidate"
    elif dti_pct > 45 or ltv_pct > 85:
        risk_level = "high"
        recommendation = "review"
    else:
        risk_level = "medium"
        recommendation = "review"
    result.update(
        {
            "dti_ratio": flat_dti,
            "ltv_ratio": flat_ltv,
            "interest_rate": round((result["interest"]["estimated_annual_rate_pct"] or 0) / 100, 6),
            "monthly_payment": result["interest"]["estimated_monthly_payment"],
            "policy_breaches": policy_breaches,
            "risk_level": risk_level,
            "recommendation": recommendation,
            "human_review_required": True,
            "explanation": [
                result["dti"]["assessment"],
                result["ltv"]["assessment"],
                "Human credit officer review required.",
            ],
        }
    )
    log_event(
        db,
        "loan_policy_scored",
        customer.id,
        {"policy_score_id": record.id, "recommendation": record.recommendation, "flowise_customer_id": payload.customer_id},
    )
    return schemas.LoanPolicyResponse(**result)


@router.post("/approval-committee/submit", response_model=schemas.ApprovalCommitteeSubmitResponse)
def submit_to_approval_committee(
    payload: schemas.ApprovalCommitteeSubmitRequest,
    db: Session = Depends(get_db),
) -> schemas.ApprovalCommitteeSubmitResponse:
    ensure_customer(db, payload.customer_id)
    policy_score_id = payload.policy_score.get("policy_score_id") or payload.policy_score.get("id")
    case = models.ApprovalCommitteeCase(
        customer_id=payload.customer_id,
        assessment_id=payload.assessment_id,
        policy_score_id=policy_score_id,
        status="submitted_to_committee",
        submitted_by=payload.submitted_by,
        notes=payload.notes,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    committee_case_id = _case_id(case.id)
    log_event(
        db,
        "approval_committee_submitted",
        _audit_customer_id(payload.customer_id),
        {"committee_case_id": committee_case_id, "policy_score_id": policy_score_id},
    )
    return schemas.ApprovalCommitteeSubmitResponse(committee_case_id=committee_case_id)


@router.post("/final-decision", response_model=schemas.FinalDecisionResponse)
def record_final_decision(
    payload: schemas.FinalDecisionRequest,
    db: Session = Depends(get_db),
) -> schemas.FinalDecisionResponse:
    decision_by = payload.decision_by or payload.decided_by
    if not decision_by:
        raise HTTPException(status_code=400, detail="decided_by or decision_by is required. LLM-only final decisions are not allowed.")
    case_id = _parse_prefixed_id(payload.committee_case_id, "COM")
    case = None
    if case_id is not None:
        case = db.query(models.ApprovalCommitteeCase).filter(models.ApprovalCommitteeCase.id == case_id).first()
        if not case:
            raise HTTPException(status_code=404, detail="Approval committee case not found")

    decision = models.FinalDecision(
        committee_case_id=_case_id(case.id) if case else None,
        customer_id=payload.customer_id,
        decision=payload.decision,
        approved_amount=payload.approved_amount,
        approved_rate_pct=payload.approved_rate_pct,
        conditions=payload.conditions,
        decision_by=decision_by,
        decision_notes=payload.decision_notes or payload.notes,
    )
    db.add(decision)
    if case:
        case.status = "final_decision_recorded"
    db.commit()
    db.refresh(decision)
    final_decision_id = _decision_id(decision.id)
    log_event(
        db,
        "final_decision_recorded",
        _audit_customer_id(payload.customer_id),
        {"decision_id": final_decision_id, "committee_case_id": payload.committee_case_id, "decision": payload.decision, "human_decision_by": decision_by},
    )
    return schemas.FinalDecisionResponse(decision_id=final_decision_id)


@router.post("/customer-decision-email/draft", response_model=schemas.CustomerDecisionEmailDraftResponse)
def draft_customer_decision_email(
    payload: schemas.CustomerDecisionEmailDraftRequest,
    db: Session = Depends(get_db),
) -> schemas.CustomerDecisionEmailDraftResponse:
    decision_label = payload.decision.capitalize()
    subject = f"Loan Application Update - {decision_label}"
    conditions = "\n".join(f"- {condition}" for condition in payload.conditions) or "- No conditions listed."
    amount_line = f"Approved amount: {payload.approved_amount:,.2f}" if payload.approved_amount else "Approved amount: Not applicable"
    rate_line = f"Approved annual rate: {payload.approved_rate_pct:.2f}%" if payload.approved_rate_pct else "Approved annual rate: Not applicable"
    reason_summary = payload.reason_summary or "Your application has completed credit appraisal and human review."
    body = (
        f"Dear Customer,\n\n"
        f"We are writing with an update on your loan application.\n\n"
        f"Decision status: {decision_label}\n"
        f"{amount_line}\n"
        f"{rate_line}\n\n"
        f"Conditions:\n{conditions}\n\n"
        f"Summary:\n{reason_summary}\n\n"
        f"This draft requires review and approval by an authorized credit officer before it is sent.\n\n"
        f"Sincerely,\n{payload.officer_name}"
    )
    draft = models.DecisionEmailDraft(
        customer_id=payload.customer_id,
        decision_id=payload.decision_id,
        customer_email=payload.customer_email,
        subject=subject,
        body=body,
        send_allowed=False,
        requires_human_approval=True,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    email_draft_id = _email_id(draft.id)
    log_event(
        db,
        "customer_decision_email_drafted",
        _audit_customer_id(payload.customer_id),
        {"email_draft_id": email_draft_id, "decision": payload.decision, "send_allowed": False},
    )
    return schemas.CustomerDecisionEmailDraftResponse(
        email_draft_id=email_draft_id,
        subject=subject,
        body=body,
        send_allowed=False,
        requires_human_approval=True,
    )
