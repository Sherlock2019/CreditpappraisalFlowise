from __future__ import annotations

import json
import sys
from typing import Any

import requests


BASE = "http://127.0.0.1:8000"


def post(path: str, payload: dict[str, Any], timeout: int = 60) -> dict[str, Any]:
    response = requests.post(f"{BASE}{path}", json=payload, timeout=timeout)
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text[:2000]}
    return {"status_code": response.status_code, "body": body}


def get(path: str, timeout: int = 20) -> dict[str, Any]:
    response = requests.get(f"{BASE}{path}", timeout=timeout)
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text[:2000]}
    return {"status_code": response.status_code, "body": body}


def main() -> int:
    results: dict[str, Any] = {}
    results["health"] = get("/health")
    results["flowise_health"] = get("/flowise/health")
    results["retrieval"] = post("/retrieval/query", {"customer_id": 1, "question": "loan risk", "top_k": 3})
    policy = post(
        "/loan-policy/score",
        {
            "customer_id": "1",
            "loan_amount": 50000,
            "collateral_value": 90000,
            "monthly_income": 8000,
            "monthly_debt_payments": 2200,
            "term_months": 60,
            "fraud_indicators": [],
            "missing_documents": ["Credit report"],
        },
    )
    results["loan_policy"] = policy
    policy_score = policy["body"] if policy["status_code"] == 200 else {}
    committee = post(
        "/approval-committee/submit",
        {
            "customer_id": "1",
            "policy_score": policy_score,
            "submitted_by": "smoke_test",
            "notes": "Live smoke test committee submission.",
        },
    )
    results["committee"] = committee
    committee_case_id = committee.get("body", {}).get("committee_case_id")
    decision = post(
        "/final-decision",
        {
            "committee_case_id": committee_case_id,
            "customer_id": "1",
            "decision": "conditional",
            "approved_amount": 45000,
            "approved_rate_pct": policy_score.get("interest", {}).get("estimated_annual_rate_pct", 0),
            "conditions": ["Human review of missing credit report required"],
            "decision_by": "smoke_test_officer",
            "decision_notes": "Smoke test only.",
        },
    )
    results["final_decision"] = decision
    decision_id = decision.get("body", {}).get("decision_id")
    results["email_draft"] = post(
        "/customer-decision-email/draft",
        {
            "customer_id": "1",
            "customer_email": "customer@example.com",
            "decision": "conditional",
            "approved_amount": 45000,
            "approved_rate_pct": policy_score.get("interest", {}).get("estimated_annual_rate_pct", 0),
            "conditions": ["Human review of missing credit report required"],
            "reason_summary": "Smoke test draft.",
            "officer_name": "Smoke Test Officer",
            "decision_id": decision_id,
        },
    )
    results["audit"] = post(
        "/audit",
        {"event_type": "live_smoke_test", "customer_id": 1, "actor": "codex", "details": {"status": "ran"}},
    )
    results["chat"] = post(
        "/chat",
        {
            "customer_id": 1,
            "message": "Give me a short credit risk summary using retrieved context.",
            "llm_provider": "local_mistral_ollama",
            "temperature": 0.2,
            "max_tokens": 500,
        },
        timeout=180,
    )
    print(json.dumps(results, indent=2)[:12000])
    failures = [name for name, result in results.items() if result["status_code"] >= 400]
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
