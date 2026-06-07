from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.audit import log_event
from app.database import get_db
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
    result = score_loan_policy(payload.model_dump())
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
    log_event(
        db,
        "loan_policy_scored",
        _audit_customer_id(result["customer_id"]),
        {"policy_score_id": record.id, "recommendation": record.recommendation},
    )
    return schemas.LoanPolicyResponse(**result)


@router.post("/approval-committee/submit", response_model=schemas.ApprovalCommitteeSubmitResponse)
def submit_to_approval_committee(
    payload: schemas.ApprovalCommitteeSubmitRequest,
    db: Session = Depends(get_db),
) -> schemas.ApprovalCommitteeSubmitResponse:
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
    case_id = _parse_prefixed_id(payload.committee_case_id, "COM")
    if case_id is None:
        raise HTTPException(
            status_code=400,
            detail="committee_case_id is required before final decision for review, high-risk, or committee workflow cases.",
        )

    case = db.query(models.ApprovalCommitteeCase).filter(models.ApprovalCommitteeCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=404, detail="Approval committee case not found")

    decision = models.FinalDecision(
        committee_case_id=_case_id(case.id),
        customer_id=payload.customer_id,
        decision=payload.decision,
        approved_amount=payload.approved_amount,
        approved_rate_pct=payload.approved_rate_pct,
        conditions=payload.conditions,
        decision_by=payload.decision_by,
        decision_notes=payload.decision_notes,
    )
    db.add(decision)
    case.status = "final_decision_recorded"
    db.commit()
    db.refresh(decision)
    final_decision_id = _decision_id(decision.id)
    log_event(
        db,
        "final_decision_recorded",
        _audit_customer_id(payload.customer_id),
        {"decision_id": final_decision_id, "committee_case_id": payload.committee_case_id, "decision": payload.decision},
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
