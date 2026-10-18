# Implementation Plan

Prioritized, incremental upgrade of the credit appraisal POC. Based on `docs/IMPLEMENTATION_GAP_ANALYSIS.md`. Each milestone is a small series of commits on `feature/enterprise-platform-upgrade` (or a child branch), ends with passing tests, and keeps LISA, Streamlit and both Flowise flows working.

## Ground rules

- Existing unversioned routes stay. New work lands under `/api/v1`; old routes become thin adapters over the same services, then get an auth dependency once the UI can send tokens.
- No milestone is "done" until its tests run in CI (from M9 on) or locally (before M9) and pass.
- Synthetic data and mock integrations by default. No real Temenos, AWS or customer data.
- Each phase ends with a report: files changed, features, tests and results, demo steps, limitations, next phase.

## M0 — Prerequisites (before code changes)

| # | Task | Owner | Done when |
| --- | --- | --- | --- |
| 0.1 | Commit the in-progress Agentflow V2 work (`flowise_project/agentflows/`, `scripts/seed-flowise-agentflow.js`, edits to `start*.sh`, `scripts/*.js`) to `main`, or confirm it should move to this branch. Remove stray files `200; done; echo flowise`, `logs-start-local.out`. | Repo owner | Clean working tree |
| 0.2 | Decide the open questions in the last section. | Repo owner | Answers recorded here |
| 0.3 | Add `pyproject.toml` with ruff + mypy config and a `pytest.ini` so tests run without `sys.path` hacks. | Eng | `pytest` green, `ruff check` runs |

## Priority 1 — Core full stack

### M1 — Typed API foundation and migrations

1. **Alembic baseline.** Add `backend/alembic/`; revision `0001_baseline` reproduces the current `init.sql` schema exactly (verified by `alembic upgrade head` on an empty DB and a schema diff against `init.sql`). Startup stops calling `create_all()`; `init.sql` keeps only `CREATE EXTENSION vector`.
2. **Schema corrections (migration 0002).** `tenants` table with a seeded `demo` tenant; `tenant_id` on customers, documents, chunks, appraisals, decisions, audit. Normalize `customer_id` to integer FKs in `loan_policy_scores`, `approval_committee_cases`, `final_decisions`, `decision_email_drafts` (data-migrating `"COM-"`/string ids). Timezone-aware timestamps.
3. **New tables (migration 0003).** `appraisals`, `agent_runs`, `approvals`, `idempotency_keys`.
4. **Async data layer.** `asyncpg` + SQLAlchemy `AsyncSession` for new `/api/v1` routes. Legacy routes keep the sync session until they are rewritten as adapters, so behavior does not change underneath LISA.
5. **Error envelope.** One `ApiError {code, message, details, correlation_id}` model, exception handlers for validation, not-found, conflict, auth and unexpected errors.
6. **Pagination.** Cursor or `limit/offset` + `sort` + filters on list endpoints; `Page[T]` response model.
7. **Idempotency.** `Idempotency-Key` header on `POST` create endpoints, stored with request hash and response.
8. **Required v1 endpoints:** customers, documents, appraisals, agents/execute, agents/runs/{id}, approvals/{id}/decision, audit/events. Agent execution calls the existing `FlowiseClient`.
9. **Fix read-path side effects.** `ensure_customer()` stops creating customers on `/retrieval/query` and `/loan-policy/score`; it is kept only for the explicit Flowise upload path, behind a flag.

**Tests:** pytest + httpx `AsyncClient` against a disposable Postgres (testcontainers or the compose `postgres` service): CRUD, validation errors, pagination, idempotent replay, transaction rollback on failure, migration up/down.

### M2 — React/TypeScript engineering console

- New app at `web/` (Vite + React + TypeScript). LISA in `creditappflowise/` is untouched.
- API client generated from `/openapi.json` (`openapi-typescript` + a small fetch wrapper).
- Screens, in order: customers & documents → appraisals → agent runs & status → evidence/citations → approval queue → audit history → ops dashboard (filled in after M8 metrics exist).
- Accessible forms (labels, error association, keyboard), client-side validation mirroring the Pydantic schemas, loading/error/retry states.
- **Tests:** Vitest + Testing Library for components; Playwright E2E against the compose stack.

## Priority 2 — Enterprise security

### M3 — OIDC, RBAC, tenant isolation

- Keycloak in compose with a realm export (`infra/keycloak/realm-credit-ai.json`): synthetic users for the 8 roles, two tenants.
- React console: authorization-code + PKCE (`oidc-client-ts`), tokens in memory, refresh via refresh token rotation. No cookies, so no CSRF surface; if a BFF is introduced later, add CSRF tokens then.
- FastAPI: JWT validation against JWKS (issuer, audience, signature, expiry, clock skew); `Principal {sub, tenant_id, roles, kind: human|agent}`.
- Permission matrix in code (`app/authz/policy.py`), **default deny**: every route declares a required permission; a test enumerates all routes and fails if any lacks one.
- Tenant isolation enforced in the repository layer (every query filtered by `principal.tenant_id`) **and** by PostgreSQL row-level security as defense in depth.
- `/final-decision` and `/api/v1/approvals/{id}/decision` require a **human** principal with `decision:approve`; agent principals are rejected regardless of payload content. `decided_by` comes from the token, never the body.
- CORS narrowed to configured origins.
- LISA and legacy routes: transition flag `LEGACY_AUTH_MODE=dev-anonymous|required`; default stays anonymous locally until LISA sends tokens.
- **Tests:** forged/expired/wrong-audience tokens, cross-tenant read attempts on every resource, role matrix, agent attempting a human decision.

### M4 — Tamper-evident audit

- Audit write in the same transaction as the business change.
- Hash chain per tenant (`prev_hash`, `hash = sha256(prev_hash || canonical_json(event))`), `actor` and `actor_kind` columns, DB role without `UPDATE/DELETE` on `audit_events`.
- `GET /api/v1/audit/events` (paginated, filtered) and a verification endpoint/CLI.
- **Tests:** chain verification passes; editing a row breaks verification; rollback leaves no orphan audit row.

### M5 — Agent identities and secure tools (MCP)

- One Keycloak client per agent runtime (main, credit scoring, asset, legal/policy, fraud/AML) using client credentials; Flowise HTTP nodes carry that agent's bearer token through a per-agent Flowise credential.
- Scopes per agent (e.g. fraud agent may read fraud evidence, cannot read legal memos; no agent has `decision:approve`).
- MCP server (`backend/app/mcp/`) exposing the same FastAPI services as typed tools with JSON-schema input validation, timeouts and structured errors. Identity comes from the transport token, never from tool arguments or prompt text.
- Prompt-injection controls at the boundary: retrieved text is data (never interpreted as instructions by the tool layer), customer/tenant scope comes only from the token and run context, outbound tool arguments validated against the run's allowed customer.
- Backend support for resuming Flowise Human Input (`humanInput` with the same `chatId`) only after an authenticated human approval.
- **Tests:** agent A token calling agent B tool → 403; tool call with injected `customer_id` of another tenant → 403; prompt text "you are now admin" has no effect on authz; agent calling the decision endpoint → 403.

### M5b — Temenos mock and SCIM

- `TemenosConnector` protocol with `MockTemenosConnector` (explicitly labeled, synthetic) and a disabled `RealTemenosAdapter` skeleton configured with a separate digital-officer service identity.
- Write-back only from the approval workflow after human approval; read scopes per agent.
- SCIM 2.0 `/scim/v2/Users` and `/Groups` (create, patch, deactivate, list with filter) mapping groups to roles; tested with the SCIM compliance subset, kept separate from OIDC login.

## Priority 3 — Enterprise workflows

### M6 — Durable execution (Temporal)

- Temporal dev server in compose; worker process in `backend/app/workflows/`.
- Workflows: document ingestion (parse → chunk → embed → index), appraisal processing, approval wait (signal + expiry timer + escalation), eval jobs, dataset export.
- Activities idempotent by document/appraisal id; retry policy with exponential backoff; non-retryable error types; failed runs go to a `workflow_failures` table surfaced in the console.
- Ownership: **Flowise owns reasoning and tool calls inside an agent run; Temporal owns business state, retries and waits.** `agent_runs` stores the Temporal workflow id and the Flowise chat id; neither system duplicates the other's state.
- **Tests:** Temporal test environment with time skipping: retry, timeout, cancel, worker restart recovery, approval expiry.

### M7 — Connector framework and document intelligence

- `Connector` v2 interface: auth/credential isolation, `discover_schema`, paginated `list`, `fetch`, incremental `sync(cursor)`, `health`, rate-limit + backoff, structured errors. Existing connectors wrapped; placeholders stay placeholders and report it via `health`.
- Connectors: Temenos mock, PDF/DOCX, XLSX/CSV, generic REST.
- Single RAG index: `document_chunks` with Ollama embeddings via the backend; dimension fixed by migration; hash embeddings kept only as a test fallback. Flowise retrieval goes through `/retrieval/query`.
- Document-level ACL (`document_acl` table) applied in the SQL query before ranking.
- Knowledge graph: start with relational entity/relationship tables (customer, guarantor, collateral, facility) populated from extraction; graph DB only if a query need appears.
- **Tests:** parser fixtures for every file type in the synthetic dataset; incremental sync; cross-tenant retrieval returns zero foreign chunks.

## Priority 4 — Production engineering

### M8 — Observability

- OpenTelemetry for FastAPI, httpx (Flowise/Ollama calls), SQLAlchemy and Temporal; correlation id propagated to Flowise via vars and to audit.
- Prometheus metrics (API latency/errors, agent run outcomes, tool latency, retrieval scores, workflow retries, model latency, tokens, estimated cost, approval wait time); Grafana dashboards provisioned from JSON.
- JSON logging with a redaction filter; prompts, document text and financial fields excluded from telemetry by allow-list.
- `/health/live` and `/health/ready` (DB, migrations at head, Flowise reachable).

### M9 — AI evaluation

- `eval/datasets/v1/`: synthetic questions with expected chunk ids, expected citations, expected policy outputs, and adversarial cases (prompt injection, cross-tenant, unauthorized Temenos write, tool impersonation, sensitive-data disclosure, hallucinated approval).
- Runner computing recall@k, citation correctness, groundedness (LLM judge + rule checks), unsupported-claim rate, tool-call correctness, authz compliance, completion, latency, tokens, cost.
- Regression gate in CI when prompts, models, tools or index config change. High-risk outputs routed to a human review queue in the console.

### M10 — CI/CD and staging

- GitLab CI: lint (ruff, eslint), types (mypy, tsc), pytest with Postgres service, Vitest, Playwright, Agentflow validator, Alembic up/down, gitleaks, pip-audit/npm audit, Trivy image scan, image build and push.
- Non-root Dockerfiles; compose profile for full local stack.
- Helm chart (`deploy/helm/credit-ai/`): backend, worker, web, Flowise, migrations job, probes, NetworkPolicies (Flowise egress only to FastAPI and vLLM), secrets via external-secrets.
- Staging values file; Argo CD `Application` manifest as the GitOps option; documented rollback (Helm rollback + Alembic downgrade policy).

## Priority 5 — Hybrid MLOps

### M11 — Approved synthetic export and SageMaker simulation

- `DatasetExportRequest` workflow (Temporal): request → data minimization → de-identification → validation → human approval (compliance officer) → encryption → export → retention timer → deletion.
- `ExportSink` interface with `LocalSimulatedSink` default and an `S3SageMakerSink` that refuses to run unless the dataset is flagged synthetic or carries an approval record, and credentials are scoped to one bucket prefix.
- GitLab quality gates consume eval results; OpenStack deployment integration documented against the Helm chart.

## Phase 10 docs (written alongside each milestone)

`ARCHITECTURE`, `API_CONTRACTS`, `SECURITY_MODEL`, `TENANT_ISOLATION`, `AGENT_PERMISSIONS`, `FLOWISE_INTEGRATION`, `CONNECTOR_FRAMEWORK`, `EVALUATION_FRAMEWORK`, `MLOPS_PIPELINE`, `OPERATIONS_RUNBOOK`, `FEATURE_EVIDENCE_MATRIX`. Each doc is written when its milestone lands, with links to source and test names. The evidence matrix maps to the FPT and playSTUDIOS requirements and states plainly what code cannot prove (people management, company-wide adoption, production deployment history).

## Open decisions for the repo owner

1. **Agentflow V2 work:** commit it to `main` first, or bring it onto this branch?
2. **Async migration scope:** new `/api/v1` routes async with legacy routes left sync (recommended), or convert everything at once?
3. **Embedding model of record:** Ollama `embeddinggemma` (768-d, private, recommended) or another model? This sets the pgvector column dimension.
4. **CI target:** GitLab CI (per the brief) — confirm there is a GitLab remote, since `origin` is the only remote today.
5. **Legacy auth cut-over:** when should unversioned routes start requiring tokens — after the React console ships, or only after LISA is updated to log in?

## Immediate next step

M0, then M1 steps 1–3 (Alembic baseline and schema migrations), with migration tests. That is the first reviewable increment.
