"""Run the Enterprise Platform workflow through FastAPI, stage by stage, and print PASS/FAIL.

Every stage on the Flowise "Enterprise Platform" lane that has code is exercised here against the
real FastAPI application. Planned stages are listed as PLANNED, not faked.

Offline (default): the real FastAPI app runs in-process on SQLite. A simulated Agentflow replays the
Flowise Agentflow's tool calls with the per-agent tokens FastAPI issues, and evidence comes from the
synthetic CUST-001 documents parsed by the real document parser. No Postgres, Flowise or LLM needed.

    .venv/bin/python scripts/demo_platform.py

Live: against a running backend (started with AUTH_DEV_MODE=true and the same AUTH_DEV_JWT_SECRET),
which calls the real Flowise Agentflow and local LLM.

    AUTH_DEV_JWT_SECRET=... .venv/bin/python scripts/demo_platform.py --live --api http://127.0.0.1:8000 --customer 2
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "bank-credit-ai-poc" / "backend"
DATASET = ROOT / "docfactor_banking_demo_dataset" / "customer_documents"
sys.path.insert(0, str(BACKEND))

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--live", action="store_true", help="run against a running backend instead of in-process")
parser.add_argument("--api", default="http://127.0.0.1:8000", help="backend URL for --live")
parser.add_argument("--customer", type=int, default=2, help="live mode customer id; 2 is CUST-001 in the local demo database (offline uses its own seeded CUST-001)")
parser.add_argument("--json", action="store_true", help="print the results as JSON")
ARGS = parser.parse_args()

if not ARGS.live:
    # In-process mode: dev auth with throwaway secrets, audit JSONL into the pytest cache folder.
    os.environ.setdefault("AUTH_DEV_MODE", "true")
    os.environ.setdefault("AUTH_DEV_JWT_SECRET", "offline-demo-dev-secret-0123456789abcdef0123")
    os.environ.setdefault("AGENT_TOKEN_SECRET", "offline-demo-agent-secret-0123456789abcdef01")
    os.environ.setdefault("AUDIT_LOG_DIR", str(ROOT / ".pytest_cache" / "demo_audit_logs"))
elif not os.environ.get("AUTH_DEV_JWT_SECRET"):
    sys.exit("--live needs AUTH_DEV_JWT_SECRET set to the backend's value (backend started with AUTH_DEV_MODE=true).")

import jwt  # noqa: E402

from app.document_parser import chunk_sections, parse_document  # noqa: E402

DEV_ISSUER, AUDIENCE = "credit-ai-dev", "credit-ai-api"


# ---------------------------------------------------------------------------
# Result bookkeeping
# ---------------------------------------------------------------------------
@dataclass
class Stage:
    key: str
    label: str
    status: str
    checks: list[tuple[str, bool | None, str]] = field(default_factory=list)

    def check(self, name: str, ok: bool | None, detail: str = "") -> bool | None:
        self.checks.append((name, ok, detail))
        return ok

    @property
    def outcome(self) -> str:
        if self.status == "planned":
            return "PLANNED"
        results = [ok for _, ok, _ in self.checks if ok is not None]
        if not results:
            return "INFO"
        return "PASS" if all(results) else "FAIL"


def lane_stages() -> list[dict]:
    """Stage list from the Flowise canvas definition, so the demo and the canvas never disagree."""
    node = shutil.which("node")
    if node:
        out = subprocess.run([node, "-e", "console.log(JSON.stringify(require('./scripts/lib/platform-canvas').STAGES))"], cwd=ROOT, capture_output=True, text=True)
        if out.returncode == 0:
            return json.loads(out.stdout)
    sys.exit("node is required to read scripts/lib/platform-canvas.js")


def human_token(user: str, roles: list[str], tenant: str = "demo") -> dict[str, str]:
    now = int(time.time())
    claims = {"iss": DEV_ISSUER, "aud": AUDIENCE, "sub": f"dev|{user}", "preferred_username": user, "roles": roles, "tenant_id": tenant, "iat": now, "exp": now + 3600}
    return {"Authorization": "Bearer " + jwt.encode(claims, os.environ["AUTH_DEV_JWT_SECRET"], algorithm="HS256")}


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Offline environment: real app on SQLite, simulated Agentflow, evidence from the synthetic documents
# ---------------------------------------------------------------------------
@functools.lru_cache
def customer_chunks(code: str) -> tuple[dict, ...]:
    chunks = []
    folder = DATASET / code
    for doc_number, path in enumerate(sorted(folder.iterdir()), start=1):
        for index, section in enumerate(chunk_sections(parse_document(str(path)), chunk_size=1200, overlap=100)):
            chunks.append({"document_id": doc_number, "chunk_index": index, "filename": path.name, "page_number": section["page_number"], "chunk_text": section["text"]})
    return tuple(chunks)


def offline_retrieval(db, customer_id: int, question: str, top_k: int = 8) -> dict:
    """Keyword-ranked stand-in for pgvector search, over the customer's real synthetic documents."""
    from app import models

    customer = db.get(models.Customer, customer_id)
    words = set(re.findall(r"[a-z]{4,}", question.lower()))
    scored = []
    for chunk in customer_chunks(customer.name):
        text = chunk["chunk_text"].lower()
        score = sum(text.count(w) for w in words) + (2 if any(w in chunk["filename"] for w in words) else 0)
        scored.append((score, chunk))
    top = [dict(chunk, score=float(score)) for score, chunk in sorted(scored, key=lambda item: -item[0])[:top_k]]
    return {"context": " ".join(c["filename"] + " " + c["chunk_text"] for c in top), "question": question, "retrieved_chunks": top}


class SimulatedAgentflow:
    """Replays the generated Agentflow's tool calls (see flowise_project/agentflows/build-agentflows.js).

    It only uses what Flowise receives: overrideConfig.vars from FastAPI. Two adversarial probes run
    inside the live run to show the gateway refusing them.
    """

    flow_id = "simulated-agentflow"

    def __init__(self, client):
        self.client = client
        self.calls: list[dict] = []
        self.probes: dict[str, tuple[int, str]] = {}
        self.approval_id: str | None = None

    def _tool(self, method: str, path: str, token: str, body: dict | None = None) -> dict:
        response = self.client.request(method, f"/api/v1/tools/{path}", json=body, headers=bearer(token))
        if response.status_code >= 400:
            raise RuntimeError(f"tool {path} returned {response.status_code}: {response.text[:200]}")
        return response.json()

    def predict(self, payload: dict) -> dict:
        self.calls.append(payload)
        v = payload["overrideConfig"]["vars"]
        customer = int(v["customer_id"])
        main = v["agent_token_main_credit_appraisal"]
        if "humanInput" in payload:
            status = self._tool("GET", f"approvals/{self.approval_id}", main)
            if not status["decision_recorded"]:
                return {"text": "### No decision recorded"}
            if payload["humanInput"]["type"] == "proceed":
                draft = self._tool("POST", "email.draft", main, {"approval_id": self.approval_id})
                self._tool("POST", "audit.event", main, {"event_type": "credit_decision_relayed", "details": {"email_draft_id": draft["email_draft_id"]}})
                return {"text": f"### Decision recorded: {status['status']} by {status['decided_by']} · email draft {draft['email_draft_id']} (not sent)"}
            self._tool("POST", "audit.event", main, {"event_type": "credit_officer_override", "details": {"status": status["status"]}})
            return {"text": f"### AI recommendation not accepted: {status['status']}"}

        # Adversarial probes: the credit agent reaching for legal evidence, and a prompt-injected customer id.
        for name, body in {
            "credit_agent_reads_legal": {"customer_id": customer, "question": "liens", "domain": "legal"},
            "injected_customer_id": {"customer_id": customer + 1, "question": "income", "domain": "credit"},
        }.items():
            r = self.client.post("/api/v1/tools/evidence.search", json=body, headers=bearer(v["agent_token_credit_scoring"]))
            self.probes[name] = (r.status_code, r.json().get("error", {}).get("message", ""))

        evidence_ids = []
        for agent, domain, question in (
            ("credit_scoring", "credit", "income salary bank statement cash flow debt"),
            ("asset_appraisal", "asset", "collateral valuation property market value"),
            ("legal_policy", "legal", "loan application agreement identity registration"),
            ("fraud_aml", "fraud", "inconsistent figures transactions statement"),
        ):
            result = self._tool("POST", "evidence.search", v[f"agent_token_{agent}"], {"customer_id": customer, "question": question, "domain": domain, "top_k": 4})
            evidence_ids += [e["chunk_id"] for e in result["evidence"]]
        policy = self._tool(
            "POST",
            "policy.score",
            main,
            {"customer_id": str(customer), "loan_amount": v["loan_amount"], "collateral_value": v["collateral_value"], "monthly_income": v["monthly_income"], "monthly_debt_payments": v["monthly_debt_payments"], "term_months": v["term_months"]},
        )
        approval = self._tool(
            "POST",
            "approval.request",
            main,
            {
                "customer_id": customer,
                "recommendation": "conditional",
                "proposed_amount": 240000,
                "proposed_rate_pct": policy["interest"]["estimated_annual_rate_pct"] or 0,
                "conditions": ["Updated collateral valuation"],
                "reason_summary": f"DTI {policy['dti']['value_pct']}%, LTV {policy['ltv']['value_pct']}% [{evidence_ids[0]}]",
                "policy_score_id": policy["policy_score_id"],
                "evidence_ids": evidence_ids,
            },
        )
        self.approval_id = approval["approval_id"]
        return {"text": "Recommendation memo ready", "action": {"data": {"nodeId": "humanInputAgentflow_0"}}}


def offline_client():
    from fastapi.testclient import TestClient
    from pgvector.sqlalchemy import Vector
    from sqlalchemy import create_engine
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.ext.compiler import compiles
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    compiles(JSONB, "sqlite")(lambda *a, **k: "JSON")
    compiles(Vector, "sqlite")(lambda *a, **k: "BLOB")

    from app import models
    from app.database import Base, get_db
    from app.main import app
    from app.routers.v1 import tools as tools_router
    from app.services.agent_runtime import get_agentflow_client

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    client = TestClient(app, raise_server_exceptions=False)
    flow = SimulatedAgentflow(client)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_agentflow_client] = lambda: flow
    tools_router.retrieve_customer_context = offline_retrieval

    db = factory()
    db.add_all(
        [
            models.Customer(id=1, name="CUST-001", tenant_id="demo"),
            models.Customer(id=2, name="CUST-002", tenant_id="demo"),
            models.Customer(id=3, name="CUST-003", tenant_id="other-bank"),
        ]
    )
    db.commit()
    db.close()
    return client, flow, factory


# ---------------------------------------------------------------------------
# The walkthrough
# ---------------------------------------------------------------------------
def run(stages: dict[str, Stage]) -> None:
    if ARGS.live:
        import httpx

        client, flow, factory = httpx.Client(base_url=ARGS.api, timeout=1800), None, None
        customer = ARGS.customer
    else:
        client, flow, factory = offline_client()
        customer = 1

    alice = human_token("alice", ["loan_officer"])
    bob = human_token("bob", ["loan_officer"])
    carol = human_token("carol", ["compliance_officer"])
    loan = {"customer_id": customer, "request": "Run a full credit appraisal and underwriting recommendation.", "loan_amount": 250000, "collateral_value": 400000, "monthly_income": 12000, "monthly_debt_payments": 1800, "term_months": 60}

    # --- OAuth 2.0 / OIDC SSO -------------------------------------------------
    s = stages["oidc_sso"]
    r = client.get("/api/v1/approvals")
    s.check("no token → 401", r.status_code == 401, r.json().get("error", {}).get("message", ""))
    forged = jwt.encode({"iss": DEV_ISSUER, "aud": AUDIENCE, "sub": "dev|mallory", "roles": ["loan_officer"], "tenant_id": "demo", "iat": int(time.time()), "exp": int(time.time()) + 600}, "not-the-real-secret-0123456789abcdef", algorithm="HS256")
    s.check("forged signature → 401", client.get("/api/v1/approvals", headers=bearer(forged)).status_code == 401)
    s.check("valid officer token → 200", client.get("/api/v1/approvals", headers=alice).status_code == 200)

    # --- Typed API -----------------------------------------------------------
    s = stages["typed_api"]
    r = client.post("/api/v1/agents/execute", json={"customer_id": "abc", "request": "x", "unexpected": True}, headers=alice)
    body = r.json()
    s.check("invalid body → 422 envelope", r.status_code == 422 and body["error"]["code"] == "validation_error", f"{len(body['error']['details'])} field errors, correlation_id={body['error']['correlation_id'][:8]}…")

    # --- Governed agent run (Agentflow) ---------------------------------------
    started = time.time()
    r = client.post("/api/v1/agents/execute", json=loan, headers={**alice, "Idempotency-Key": f"demo-{int(started)}"})
    run_ = r.json()
    elapsed = time.time() - started
    replay = client.post("/api/v1/agents/execute", json=loan, headers={**alice, "Idempotency-Key": f"demo-{int(started)}"}).json()
    s.check("Idempotency-Key replays the same run", replay.get("id") == run_.get("id"), run_.get("id", "")[:8])

    s = stages["agents_tools"]
    s.check("run reaches the human approval gate", run_.get("status") == "awaiting_approval", f"status={run_.get('status')} in {elapsed:.0f}s {run_.get('error') or ''}"[:220])
    approval = run_.get("approval") or {}

    s = stages["async_distributed"]
    s.check("flow paused with a pending approval", approval.get("status") == "pending", f"approval {approval.get('id', '')[:8]}… expires {approval.get('expires_at', '')[:16]}")

    s = stages["credentials"]
    if flow:
        vars_sent = flow.calls[0]["overrideConfig"]["vars"]
        tokens = [k for k in vars_sent if k.startswith("agent_token_")]
        s.check("one run-bound token per agent identity", len(tokens) == 7, ", ".join(t.replace("agent_token_", "") for t in tokens))
        s.check("no token in the LLM-visible question", "agent_token" not in flow.calls[0]["question"])
        from app.auth.tokens import mint_agent_token

        agent = mint_agent_token("main_credit_appraisal", run_id=run_.get("id", "x"), tenant_id="demo", customer_id=customer)
        r = client.post("/api/v1/agents/execute", json=loan, headers=bearer(agent))
        s.check("agent token cannot start runs (human-only) → 403", r.status_code == 403, r.json()["error"]["message"])
        r = client.post("/api/v1/tools/evidence.search", json={"customer_id": customer, "question": "q", "domain": "credit"}, headers=bearer(vars_sent["agent_token_credit_scoring"]))
        s.check("tokens are dead while the run waits for a human → 403", r.status_code == 403, r.json()["error"]["message"])
    else:
        s.check("agent tokens are minted server-side (not visible to this client)", None, "covered offline and by tests/test_agent_gateway.py")

    s = stages["mcp_gateway"]
    if flow:
        for probe, (code, message) in flow.probes.items():
            s.check(f"{probe.replace('_', ' ')} → 403", code == 403, message)
        from app.auth.tokens import mint_agent_token

        fraud = mint_agent_token("fraud_aml", run_id="x", tenant_id="demo", customer_id=customer)
        tools = [t["name"] for t in client.get("/api/v1/tools/manifest", headers=bearer(fraud)).json()["tools"]]
        s.check("fraud agent's manifest is scope-filtered", tools == ["evidence.search"], f"tools={tools}")
    r = client.get("/api/v1/tools/manifest", headers=alice)
    s.check("human token refused by the tool gateway → 403", r.status_code == 403)

    # --- Multi-tenant RBAC -----------------------------------------------------
    s = stages["tenant_rbac"]
    outsider = human_token("oscar", ["loan_officer", "compliance_officer"], tenant="other-bank")
    s.check("other tenant cannot start a run on this customer → 404", client.post("/api/v1/agents/execute", json=loan, headers=outsider).status_code == 404)
    if approval:
        s.check("other tenant cannot see the approval → 404", client.get(f"/api/v1/approvals/{approval['id']}", headers=outsider).status_code == 404)
        r = client.post(f"/api/v1/approvals/{approval['id']}/decision", json={"decision": "rejected"}, headers=human_token("dana", ["credit_analyst"]))
        s.check("credit analyst (no approval:decide) → 403", r.status_code == 403, r.json()["error"]["message"])
    s.check("platform admin gets no tenant data → 403", client.get("/api/v1/approvals", headers=human_token("root", ["platform_admin"])).status_code == 403)

    # --- Human approval gate ---------------------------------------------------
    s = stages["human_approval"]
    if approval:
        url = f"/api/v1/approvals/{approval['id']}/decision"
        r = client.post(url, json={"decision": "approved", "approved_amount": 240000, "approved_rate_pct": 7.5}, headers=alice)
        s.check("four-eyes: the officer who started the run → 403", r.status_code == 403, r.json()["error"]["message"])
        r = client.post(url, json={"decision": "conditional", "approved_amount": 230000, "approved_rate_pct": 7.75, "conditions": ["Updated collateral valuation within 30 days"], "notes": "Reduced amount"}, headers=bob)
        decided = r.json()
        s.check("second officer records the decision → 200", r.status_code == 200 and decided["approval"]["decided_by"] == "bob", f"decision={decided.get('approval', {}).get('status')}")
        s.check("FastAPI resumed the flow to completion", decided.get("run", {}).get("status") == "completed", (decided.get("run", {}).get("answer") or decided.get("resume_error") or "")[:160])
        stages["async_distributed"].check("resume after the human decision", decided.get("run", {}).get("status") == "completed")
    else:
        s.check("approval available", False, "the run did not reach the gate; see the agents stage")

    # --- Observability -----------------------------------------------------------
    s = stages["observability"]
    r = client.get("/api/v1/approvals", headers={**alice, "X-Correlation-ID": "demo-trace-42"})
    s.check("X-Correlation-ID is echoed", r.headers.get("X-Correlation-ID") == "demo-trace-42")
    events = client.get("/api/v1/audit/events", params={"run_id": run_.get("id"), "limit": 200}, headers=carol).json().get("items", [])
    s.check("every run event carries the run's correlation id", bool(events) and all(e["correlation_id"] == run_.get("correlation_id") for e in events if e["event_type"].startswith("agent_tool")), f"{len(events)} events")

    # --- Audit -------------------------------------------------------------------
    s = stages["audit_chain"]
    agents_seen = sorted({e["actor"] for e in events if e["actor_kind"] == "agent"})
    stages["agents_tools"].check("each specialist called tools under its own identity", {"agent:credit_scoring", "agent:asset_appraisal", "agent:legal_policy", "agent:fraud_aml", "agent:main_credit_appraisal"} <= set(agents_seen), ", ".join(agents_seen))
    s.check("decision, tool calls and denials are audited", {"credit_decision_recorded", "agent_tool_evidence_search", "agent_tool_denied"} <= {e["event_type"] for e in events} if flow else any(e["event_type"] == "credit_decision_recorded" for e in events), f"{len(events)} events for this run")
    verify = client.get("/api/v1/audit/verify", headers=carol).json()
    s.check("hash chain verifies", verify.get("valid") is True, f"{verify.get('events_checked')} events, head {str(verify.get('head_hash'))[:12]}…")
    if factory:
        from app import models

        db = factory()
        row = db.query(models.AuditEvent).filter(models.AuditEvent.event_type == "approval_requested").first()
        row.details = {**row.details, "ai_recommendation": "approved"}
        db.commit()
        db.close()
        tampered = client.get("/api/v1/audit/verify", headers=carol).json()
        s.check("editing one row breaks the chain", tampered["valid"] is False, f"first invalid event #{tampered['first_invalid_event_id']}")

    # --- Documents, spreadsheets and the data pipeline ---------------------------
    s = stages["documents"]
    for path in sorted((DATASET / "CUST-001").iterdir()):
        sections = parse_document(str(path))
        s.check(f"parse {path.suffix[1:].upper():<4} {path.name}", bool(sections) and any(x["text"].strip() for x in sections), f"{len(sections)} sections")
    s = stages["data_pipeline"]
    chunks = customer_chunks("CUST-001")
    ids = {f"chunk_{c['document_id']}_{c['chunk_index']}" for c in chunks}
    s.check("parse → chunk with unique citation ids", len(ids) == len(chunks), f"{len(chunks)} chunks from 6 files")
    if flow:
        s.check("evidence search returned cited chunks to the agents", bool(flow.calls) and any(e["event_type"] == "agent_tool_evidence_search" and e["details"]["evidence_ids"] for e in events))

    # --- Connectors -----------------------------------------------------------------
    s = stages["connectors"]
    options = client.get("/connectors/options").json().get("connectors", [])
    s.check("connector catalogue served by FastAPI", bool(options), ", ".join(str(o.get("source_type") or o.get("value") or o) for o in options)[:200])

    # --- AI evaluation ------------------------------------------------------------------
    s = stages["ai_evaluation"]
    node = shutil.which("node")
    if node:
        out = subprocess.run([node, "flowise_project/agentflows/validate-agentflows.js"], cwd=ROOT, capture_output=True, text=True, timeout=120)
        s.check("adversarial Agentflow scenarios", out.returncode == 0, f"{out.stdout.count('  ok  ')} scenarios ok, {out.stdout.count('ERR')} errors")

    # --- Informational stages -------------------------------------------------------------
    stages["postgres_model"].check("data model exercised (runs, approvals, audit, decisions)", None, "SQLite in offline mode; PostgreSQL + pgvector with --live")
    stages["automated_testing"].check("full suite", None, ".venv/bin/python -m pytest tests -q")
    stages["docker_cloud"].check("containers", None, "docker compose -f bank-credit-ai-poc/docker-compose.yml up")


def main() -> int:
    import logging

    # Keep the walkthrough readable: the app logs every request at INFO.
    logging.disable(logging.INFO)
    stages = {s["key"]: Stage(s["key"], s["label"], s["status"]) for s in lane_stages()}
    run(stages)
    if ARGS.json:
        print(json.dumps([{"key": s.key, "label": s.label, "status": s.status, "outcome": s.outcome, "checks": s.checks} for s in stages.values()], indent=2))
    else:
        mode = f"LIVE against {ARGS.api}" if ARGS.live else "OFFLINE (in-process FastAPI, SQLite, simulated Agentflow)"
        print(f"\nEnterprise Platform walkthrough · {mode}\n")
        for s in stages.values():
            print(f"{s.outcome:<8} [{s.status.capitalize()}] {s.label}")
            for name, ok, detail in s.checks:
                mark = "  ✓" if ok else ("  ✗" if ok is False else "  ·")
                print(f"{mark} {name}" + (f"  — {detail}" if detail else ""))
        counts = {o: sum(1 for s in stages.values() if s.outcome == o) for o in ("PASS", "FAIL", "INFO", "PLANNED")}
        print("\n" + " · ".join(f"{k} {v}" for k, v in counts.items()))
    return 1 if any(s.outcome == "FAIL" for s in stages.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
