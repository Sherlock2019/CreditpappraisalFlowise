from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bank-credit-ai-poc" / "backend"))

from app.flowise.schemas import FlowiseRuntimeVars
from app.policy.loan_policy import score_loan_policy
from app.services import retrieval_service


def test_retrieval_service_returns_context_citations_and_chunks(monkeypatch):
    chunks = [
        {
            "filename": "Customer_A.pdf",
            "document_type": "financial_statement",
            "page_number": 2,
            "chunk_index": 4,
            "chunk_text": "Revenue increased and debt service is stable.",
            "score": 0.91,
        }
    ]
    monkeypatch.setattr(retrieval_service, "retrieve_relevant_chunks", lambda db, customer_id, question, top_k=8: chunks)
    monkeypatch.setattr(retrieval_service, "build_context", lambda retrieved: "RAG CONTEXT")
    monkeypatch.setattr(retrieval_service, "citations_from_chunks", lambda retrieved: [{"filename": "Customer_A.pdf", "page_number": 2}])

    result = retrieval_service.retrieve_customer_context(db=None, customer_id=1, question="risk?", top_k=5)

    assert result["customer_id"] == 1
    assert result["context"] == "RAG CONTEXT"
    assert result["citations"] == [{"filename": "Customer_A.pdf", "page_number": 2}]
    assert result["retrieved_chunks"] == chunks


def test_policy_score_maps_into_flowise_runtime_vars():
    score = score_loan_policy(
        {
            "customer_id": "1",
            "loan_amount": 50_000,
            "collateral_value": 90_000,
            "monthly_income": 8_000,
            "monthly_debt_payments": 2_200,
            "term_months": 60,
            "fraud_indicators": [],
            "missing_documents": ["Credit report"],
        }
    )

    vars = FlowiseRuntimeVars(
        customer_id=score["customer_id"],
        loan_amount=50_000,
        collateral_value=90_000,
        monthly_income=8_000,
        monthly_debt_payments=2_200,
        term_months=60,
        dti_pct=score["dti"]["value_pct"],
        dti_band=score["dti"]["band"],
        ltv_pct=score["ltv"]["value_pct"],
        ltv_band=score["ltv"]["band"],
        estimated_annual_rate_pct=score["interest"]["estimated_annual_rate_pct"],
        estimated_monthly_payment=score["interest"]["estimated_monthly_payment"],
        policy_recommendation=score["policy"]["recommendation"],
        committee_required=score["policy"]["committee_required"],
        reason_codes=score["policy"]["reason_codes"],
    )

    assert vars.customer_id == "1"
    assert vars.dti_pct == 27.5
    assert vars.ltv_pct == 55.56
    assert vars.policy_recommendation == "Conditionally Acceptable"
    assert vars.committee_required is False
