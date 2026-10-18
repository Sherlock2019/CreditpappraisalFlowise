# Agent and Role Permissions

Source of truth: `bank-credit-ai-poc/backend/app/auth/agent_permissions.json` (agents) and `app/auth/policy.py` (human roles). The policy is default-deny: a permission not listed is refused.

## Agent runtime identities

Each Flowise agent calls FastAPI with its own run-bound token. Scopes are read from the registry at request time, so removing a scope takes effect immediately, even for tokens already issued.

| Agent | Scopes | Used by Agentflow nodes |
| --- | --- | --- |
| `main_credit_appraisal` | `tool:policy.score`, `tool:approval.request`, `tool:approval.read`, `tool:email.draft`, `tool:audit.write` | Credit rules, approval request, approval status, email draft, audit |
| `credit_scoring` | `tool:evidence.search:credit` | Credit evidence search |
| `asset_appraisal` | `tool:evidence.search:asset` | Asset evidence search |
| `legal_policy` | `tool:evidence.search:legal` | Legal evidence search |
| `fraud_aml` | `tool:evidence.search:fraud` | Fraud evidence search |
| `loan_officer_qa` | `tool:evidence.search:qa`, `tool:audit.write` | Q&A branch |
| `evaluation_judge` | `tool:audit.write` | Staging evaluation event |

No agent holds `approval:decide`, `agent:execute` or any human permission. `tests/test_tool_schemas.py::test_no_agent_holds_a_human_or_decision_permission` enforces this.

## Human roles

| Role | Permissions |
| --- | --- |
| Loan Officer (`loan_officer`) | customer:read, evidence:read, agent:execute, agent_run:read, approval:read, approval:decide |
| Credit Analyst (`credit_analyst`) | customer:read, evidence:read, agent:execute, agent_run:read, approval:read |
| Asset Analyst (`asset_analyst`) | customer:read, evidence:read, agent_run:read, approval:read |
| Fraud Analyst (`fraud_analyst`) | customer:read, evidence:read, agent_run:read, audit:read |
| Compliance Officer (`compliance_officer`) | customer:read, agent_run:read, approval:read, audit:read, audit:verify |
| Tenant Administrator (`tenant_admin`) | tenant:admin, agent_run:read, audit:read, audit:verify |
| Platform Administrator (`platform_admin`) | platform:admin, audit:verify (no tenant data) |
| AI Agent Runtime (`ai_agent_runtime`) | none; stripped from human tokens. Agents get scopes only from the registry |

`approval:decide` and `agent:execute` are human-only: an agent principal is refused even if a scope with that name were added.

## Tenant scope

Every principal carries one `tenant_id` (OIDC claim `OIDC_TENANT_CLAIM`, or the agent token's run). Customers, runs, approvals and audit events are filtered by it. A resource in another tenant returns 404, so its existence is not disclosed.
