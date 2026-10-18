"""Export the agent tool input schemas (Pydantic) for the Agentflow validator.

    .venv/bin/python scripts/export_tool_schemas.py

tests/test_tool_schemas.py fails if the committed file drifts from the models.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bank-credit-ai-poc" / "backend"))
OUTPUT = ROOT / "flowise_project" / "agentflows" / "tool-schemas.json"


def tool_schemas() -> dict:
    from app.schemas import LoanPolicyRequest
    from app.schemas_v1 import ApprovalRequestInput, AuditEventInput, EmailDraftInput, EvidenceSearchInput

    models = {
        "evidence.search": EvidenceSearchInput,
        "policy.score": LoanPolicyRequest,
        "approval.request": ApprovalRequestInput,
        "email.draft": EmailDraftInput,
        "audit.write": AuditEventInput,
    }
    return {name: model.model_json_schema() for name, model in models.items()}


def render() -> str:
    return json.dumps(tool_schemas(), indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    OUTPUT.write_text(render(), encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)}")
