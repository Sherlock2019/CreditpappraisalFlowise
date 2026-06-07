from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bank-credit-ai-poc" / "backend"))

from app.policy.loan_policy import calculate_dti, calculate_ltv, score_loan_policy


def score(dti_pct: float, ltv_pct: float, fraud_indicators: list[str] | None = None):
    monthly_income = 10_000
    collateral_value = 100_000
    return score_loan_policy(
        {
            "customer_id": "test",
            "loan_amount": collateral_value * ltv_pct / 100,
            "collateral_value": collateral_value,
            "monthly_income": monthly_income,
            "monthly_debt_payments": monthly_income * dti_pct / 100,
            "term_months": 60,
            "fraud_indicators": fraud_indicators or [],
            "missing_documents": [],
        }
    )


def test_dti_25_ltv_55_conditionally_acceptable():
    result = score(25, 55)
    assert result["dti"]["band"] == "Excellent"
    assert result["ltv"]["band"] == "Low"
    assert result["policy"]["recommendation"] == "Conditionally Acceptable"


def test_dti_35_ltv_70_good_medium_conditionally_acceptable():
    result = score(35, 70)
    assert result["dti"]["band"] == "Good"
    assert result["ltv"]["band"] == "Medium"
    assert result["policy"]["recommendation"] == "Conditionally Acceptable"


def test_dti_42_ltv_75_manual_review_required():
    result = score(42, 75)
    assert result["dti"]["band"] == "Review"
    assert result["policy"]["recommendation"] == "Manual Review Required"


def test_dti_47_ltv_82_high_risk_committee_required():
    result = score(47, 82)
    assert result["dti"]["band"] == "High Risk"
    assert result["ltv"]["band"] == "High"
    assert result["policy"]["recommendation"] == "High Risk / Approval Committee Required"
    assert result["policy"]["committee_required"] is True


def test_dti_52_ltv_65_decline_recommended():
    result = score(52, 65)
    assert result["dti"]["band"] == "Often Declined"
    assert result["policy"]["recommendation"] == "Decline Recommended"


def test_dti_30_ltv_95_high_risk_committee_required():
    result = score(30, 95)
    assert result["ltv"]["band"] == "Very High"
    assert result["policy"]["recommendation"] == "High Risk / Approval Committee Required"
    assert result["policy"]["committee_required"] is True


def test_high_fraud_severity_requires_enhanced_due_diligence():
    result = score(25, 55, fraud_indicators=["suspicious_invoice_duplication"])
    assert result["fraud"]["severity"] == 3
    assert result["policy"]["recommendation"] == "Enhanced Due Diligence Required"
    assert result["policy"]["committee_required"] is True


def test_monthly_income_zero_is_insufficient_evidence():
    result = calculate_dti(monthly_debt_payments=1000, monthly_income=0)
    assert result["value_pct"] is None
    assert result["band"] == "Insufficient Evidence"


def test_collateral_value_zero_is_insufficient_evidence():
    result = calculate_ltv(loan_amount=50_000, collateral_value=0)
    assert result["value_pct"] is None
    assert result["band"] == "Insufficient Evidence"
