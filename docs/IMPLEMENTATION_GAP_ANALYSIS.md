# Implementation Gap Analysis

Audit of the credit appraisal POC against the enterprise upgrade target. Every status below is backed by a file in the repository or a command that was run. Nothing is marked complete without a passing test.

- **Audited commit:** `ead27c3` (branch `main`), audited 2026-10-18 on branch `feature/enterprise-platform-upgrade`.
- **Working tree at audit time:** uncommitted edits to `scripts/ensure-flowise-flows.js`, `scripts/seed-flowise-credit-app.js`, `start-flowise.sh`, `start.sh`; untracked `flowise_project/agentflows/` and `scripts/seed-flowise-agentflow.js`. The Agentflow V2 work exists only in the working tree and is not committed yet.

## Status legend

| Status | Meaning |
| --- | --- |
| **Existing and tested** | Code exists and an automated test or validator exercises it and passes. |
| **Existing but incomplete** | Code exists but is untested, partial, or lacks a required property (auth, isolation, durability…). |
| **Missing** | No implementation in the repository. |
| **Proposed external integration** | Appears in diagrams, prompts or docs only; depends on a system not present locally. |

## 1. Baseline evidence

| Check | Command | Result |
| --- | --- | --- |
| Backend unit tests | `.venv/bin/python -m pytest tests -q` | **13 passed** (loan policy ×9, retrieval service ×2, Flowise client ×2) |
| Agentflow V2 validator | `node flowise_project/agentflows/validate-agentflows.js` | **15/15 dry-run paths ok** (5 paths × local-dev, OpenStack prod, AWS staging) with mocked FastAPI/LLM |
| API tests (HTTP layer) | — | None exist |
| DB integration tests | — | None exist |
| Frontend tests | — | None exist |
| CI pipeline | — | None exists |

## 2. Repository inventory

| Area | What exists | Location |
| --- | --- | --- |
| Backend | FastAPI 0.115, Pydantic 2.10, SQLAlchemy 2.0 (sync, psycopg2), pgvector 0.3. ~4.5k lines. 12 routers, 32 routes, unversioned paths (`/customers`, `/chat`, `/final-decision`…). | `bank-credit-ai-poc/backend/app/` |
| Database | PostgreSQL 16 + pgvector. 11 tables created by `init.sql` **and** `Base.metadata.create_all()` at startup. No migrations. | `bank-credit-ai-poc/db/init.sql`, `app/models.py` |
| Primary UI (LISA) | Vanilla HTML/CSS/JS (~1.7k lines JS), served by `web_proxy.py` which proxies `/api/*` to FastAPI. | `creditappflowise/`, `web_proxy.py` |
| Secondary UI | Streamlit legacy operator UI. | `bank-credit-ai-poc/frontend/streamlit_app.py` |
| Root-level HTML/JS | Older dashboards (`index.html`, `banking-main.js`, `docfactor-ui.js` copies…). Launched by `startallagent.sh`. | repo root |
| Flowise Chatflow | RAG chatflow (id `6f946e8b-…`) seeded from stock nodes; JSON exports committed. | `flowise_project/generated/`, `scripts/seed-flowise-credit-app.js` |
| Flowise Agentflow V2 | Generator + validator + 3 per-environment flows (43–46 nodes: 12 LLM, 28 HTTP, 20 custom function, 3 condition, human input). **Uncommitted.** | `flowise_project/agentflows/` |
| LLM providers | Ollama, OpenAI, DeepSeek, custom OpenAI-compatible, with factory and fallback. | `app/llm_providers/` |
| Policy engine | Deterministic DTI/LTV/rate/fraud-severity rules. | `app/policy/loan_policy.py` |
| Connectors | `BaseConnector` (test/list/download). S3 is real (boto3). SharePoint, OpenText, Hyland, FileNet, ServiceNow, Salesforce, cloud storage are `PlaceholderConnector`s. | `app/connectors/` |
| Containers | Backend and Streamlit Dockerfiles; `docker-compose.yml` (postgres, backend, streamlit, optional Flowise). | `bank-credit-ai-poc/` |
| Launch scripts | `start.sh` (≈22 KB) brings up Docker stack, local Flowise, Ollama, UI. | repo root |
| Synthetic dataset | 15 synthetic customers (CUST-001…015): PDF, DOCX, CSV, XLSX master. | `docfactor_banking_demo_dataset/` |

## 3. Data and credential handling

- `bank-credit-ai-poc/.env` and `.env.local` exist locally and **are git-ignored** (`.gitignore` rules `.env`, `.env.*`). Their contents were not read or printed.
- A scan of tracked files for common secret patterns (OpenAI keys, AWS key IDs, private keys) found none.
- Dev-default database credentials (`credit_ai_user` / `credit_ai_password`) are hard-coded in `docker-compose.yml`, `app/config.py` and as a fallback in `scripts/ensure-flowise-flows.js:102`. Acceptable for local dev only; must move to secrets for any shared environment.
- The demo dataset is described as synthetic in `docfactor_banking_demo_dataset/README.md`. No real banking data was identified.

## 4. Critical findings (fix before any non-local exposure)

Ranked by risk. These are the reasons the platform must not be shown as "enterprise-ready" in its current form.

1. **No authentication on any endpoint.** `app/security.py` returns a hard-coded user and is not imported by any router. Every route, including `/final-decision`, is anonymous.
2. **Human approval is asserted, not authenticated.** `/final-decision` accepts any non-empty `decided_by` string (`routers/loan_policy.py:154`). Flowise (and therefore any LLM-driven path, or any HTTP caller) can record a "human" decision. The Agentflow's Human Input node is enforced only inside Flowise.
3. **CORS allows any origin with credentials.** `main.py:32` sets `allow_origin_regex=r"https?://.*"` with `allow_credentials=True`, which defeats the explicit allow-list above it.
4. **No tenant model; cross-customer retrieval by design.** `/chat` with `customer_id <= 0` calls `retrieve_relevant_chunks_all_customers` (`rag.py:71`), which searches every customer's chunks. Per-customer isolation relies on a SQL filter plus a filename/text regex heuristic (`rag.py:20`).
5. **Flowise RAG path bypasses FastAPI authorization.** The chatflow's Postgres vector-store node queries `flowise_rag_chunks` directly; customer scoping comes from `pgMetadataFilter`, which the caller supplies through `overrideConfig`.
6. **Read endpoints create records.** `ensure_customer()` (`flowise_compat.py:8`) inserts a new customer for any unknown string id; it is called from `/retrieval/query` and `/loan-policy/score`.
7. **Audit is mutable and non-atomic.** `audit_logs` is a plain table with no integrity chain; `log_event` commits separately after the business commit, so a crash between them loses the audit record. The `actor` field is written only to the JSONL file, not the database row.

## 5. Capability classification

### Phase 1 — Typed Python APIs and PostgreSQL

| Capability | Status | Evidence / gap |
| --- | --- | --- |
| Pydantic request/response schemas | Existing but incomplete | `app/schemas.py` (365 lines) covers most routes; `/audit` and `/retrieval/query` return untyped `dict`. Several fields are loose (`dict[str, Any]`, `str \| int` ids). |
| Input validation | Existing but incomplete | File-suffix allow-list on upload; no upload size limit; `top_k` bounded. Customer ids are inconsistent types (`int` in `customers`/`documents`, `TEXT` in `loan_policy_scores`, `final_decisions`, etc.). |
| Standardized error responses | Missing | Ad-hoc `HTTPException(detail=str)`; no error envelope or codes. |
| OpenAPI docs | Existing but incomplete | FastAPI default `/docs`; no auth schemes, examples or error models. |
| Async routes + async DB | Existing but incomplete | 4 routes are `async def`, but they use the **sync** `Session`, which blocks the event loop (e.g. `/chat`). |
| Alembic migrations | Missing | Schema is `init.sql` + `create_all()`; `ALTER TABLE … IF NOT EXISTS` used ad hoc. |
| Pagination / filtering / sorting | Missing | `GET /customers` and `GET /documents` return full lists. |
| Idempotency | Missing | Uploads dedupe by a separate `/documents/deduplicate` call, not by idempotency key. |
| Transactions / rollback | Existing but incomplete | Each route commits; no explicit rollback handling; audit outside the business transaction. |
| API versioning `/api/v1/*` | Missing | All paths unversioned. The 10 required v1 endpoints do not exist; `appraisals`, `agents/execute`, `agents/runs`, `approvals/{id}/decision`, `GET audit/events` have no equivalent. |

### Phase 2 — React / TypeScript frontend

| Capability | Status | Evidence / gap |
| --- | --- | --- |
| LISA workspace | Existing but incomplete | Vanilla JS in `creditappflowise/`; works with current unversioned API; untested. |
| React/TS app | Missing | No `package.json`, `tsconfig`, or React code. Must be added as a separate app to avoid disrupting LISA. |
| Typed OpenAPI client | Missing | — |
| Screens: customers/docs, appraisals, agent runs, citations, approval queue, audit, ops dashboard | Missing (React); partial in LISA | LISA covers customers, uploads, chat with citations, policy score, committee submit, final decision, email draft. No approval queue, audit viewer, agent-run view or ops dashboard. |
| Component / E2E tests | Missing | — |
| Identity-scoped UI | Missing | No identity exists. |

### Phase 3 — Authentication, SSO, multi-tenancy

| Capability | Status | Evidence / gap |
| --- | --- | --- |
| OIDC auth code + PKCE | Missing | `security.py` is a TODO stub. |
| Token validation (iss/aud/sig/exp) | Missing | — |
| Refresh tokens | Missing | — |
| RBAC, 8 roles, default-deny | Missing | No roles, no permission checks. |
| Tenant isolation | Missing | No `tenant_id` column anywhere. |
| Secrets management | Existing but incomplete | `.env` via pydantic-settings, git-ignored; no vault/K8s secrets; dev passwords hard-coded. |
| Tamper-evident audit | Missing | Plain mutable table (finding 7). |
| CSRF | Missing | Not applicable until cookie sessions exist; CORS currently wide open (finding 3). |
| Per-agent runtime identity | Missing | Flowise calls FastAPI anonymously (Agentflow README step 5 notes this). |
| Temenos digital-officer identities | Proposed external integration | Temenos is named only in Agentflow prompt text; no adapter, mock or config. |
| SCIM 2.0 | Missing | — |

### Phase 4 — Durable asynchronous workflows

| Capability | Status | Evidence / gap |
| --- | --- | --- |
| Durable workflow engine (Temporal or equivalent) | Missing | Ingestion, embedding and appraisal run inline in HTTP requests. |
| Retries with backoff | Existing but incomplete | Only `FlowiseClient` retries (linear 0.25 s × attempt, 2 retries) — `app/flowise/client.py`. Tested. |
| Timeouts / cancellation | Existing but incomplete | Flowise 600 s, proxy 900 s; no cancellation. |
| Recovery after restart | Existing but incomplete | `document_recovery.py` re-registers files on disk at startup; not a workflow recovery mechanism. |
| Human approval wait with expiry/escalation | Missing | Flowise Human Input pauses the flow; backend client cannot resume it (Agentflow README). No expiry. |
| Correlation IDs | Existing but incomplete | `session_id` passed through Flowise vars and audit; no request-level trace id. |

### Phase 5 — Flowise Agentflow V2 / MCP security

| Capability | Status | Evidence / gap |
| --- | --- | --- |
| Agentflow V2 exported as JSON | Existing and tested | 3 generated flows + validator, 15 paths pass. **Uncommitted.** |
| Specialist agents (credit, asset, legal, fraud) | Existing and tested (as Flowise LLM nodes) | In the Agentflow graph; they share one Flowise process and one anonymous FastAPI identity. |
| Deterministic scoring outside the LLM | Existing and tested | `/loan-policy/score` called by the flow; `tests/test_loan_policy.py`. |
| Human approval gate | Existing but incomplete | Flowise Human Input node; not authenticated at the FastAPI boundary (finding 2). |
| Per-agent identity and tool scopes | Missing | — |
| MCP tools with schemas | Missing | Tools are Flowise HTTP nodes calling FastAPI; no MCP server. |
| Prompt-injection defenses at tool boundary | Missing | Bodies built with `JSON.stringify` (prevents JSON breakage, not authorization bypass). |
| Impersonation / unauthorized tool tests | Missing | — |

### Phase 6 — Connectors and document intelligence

| Capability | Status | Evidence / gap |
| --- | --- | --- |
| Connector interface | Existing but incomplete | `BaseConnector` has test/list/download only; no pagination, rate limits, backoff, health, incremental sync, structured errors. |
| S3 connector | Existing but incomplete | Real boto3 implementation; untested. |
| SharePoint, OpenText, Hyland, FileNet, ServiceNow, Salesforce | Existing but incomplete (placeholders) | Return "not implemented yet". |
| Temenos mock connector | Missing | — |
| PDF / DOCX ingestion | Existing but incomplete | `document_parser.py` (PyMuPDF, pdfplumber, docx); untested; inline, not durable. |
| XLSX / CSV ingestion | Existing but incomplete | pandas/openpyxl parsing; untested. |
| Generic REST connector | Missing | — |
| Embeddings | Existing but incomplete | FastAPI path uses OpenAI if a key is set, else a **lexical hash embedding** (`embeddings.py`), not semantic. Flowise path uses Ollama `embeddinggemma` in a separate table. Two independent RAG indexes. |
| Knowledge graph / ontology | Missing | No graph store or ontology code. |
| Document-level ACL before retrieval | Missing | Customer-level filter only; Flowise path bypasses it (finding 5). |

### Phase 7 — AI evaluation and safety

| Capability | Status | Evidence / gap |
| --- | --- | --- |
| Versioned eval dataset | Missing | Synthetic documents exist, but no labelled Q/A, expected citations or expected decisions. |
| recall@k, citation correctness, groundedness, hallucination rate | Missing | — |
| Tool-call correctness, authz compliance | Missing | Agentflow validator checks wiring and JSON bodies with mocks, not model behavior. |
| Latency / token / cost tracking | Missing | — |
| Adversarial tests | Missing | — |
| Evaluation judge | Proposed external integration | LLM judge node exists only in the AWS staging Agentflow. |
| "Human review required" invariant | Existing but incomplete | Enforced in prompts and response text; `human_review_required=True` hard-coded. Not a tested invariant at the API boundary. |

### Phase 8 — Observability and SRE

| Capability | Status | Evidence / gap |
| --- | --- | --- |
| Health endpoint | Existing but incomplete | `GET /health`, `GET /flowise/health`; no readiness probe checking DB. |
| Structured JSON logging | Missing | Plain-text `logging.basicConfig`; 8 log calls in backend. |
| OpenTelemetry, Prometheus, Grafana | Missing | — |
| Telemetry redaction | Existing but incomplete | `redact_sensitive_config` masks secret-named keys in audit details; prompts/answers are stored in audit verbatim. |

### Phase 9 — CI/CD and deployment

| Capability | Status | Evidence / gap |
| --- | --- | --- |
| Dockerfiles + Compose | Existing but incomplete | Backend/Streamlit images run as root; no Flowise/Ollama health checks; LISA UI not containerized. |
| Lint / type checks | Missing | — |
| GitLab CI / any CI | Missing | — |
| Dependency, secret, image scanning | Missing | — |
| Kubernetes / Helm | Missing | vLLM service URLs referenced in Agentflow config only. |
| GitOps (Argo CD / Flux) | Missing | — |
| Staging environment | Proposed external integration | AWS staging Agentflow exists; no infra. |
| AWS SageMaker pipeline | Proposed external integration | Not present. |
| OpenStack production | Proposed external integration | Not present. |

## 6. Architecture diagram vs. code

| Diagram component | Reality |
| --- | --- |
| LISA workspace | Implemented (vanilla JS). |
| FastAPI customer/document/audit APIs | Implemented, unversioned, unauthenticated. |
| Flowise Chatflow RAG | Implemented and committed. |
| Flowise Agentflow V2 with specialist agents and human approval | Implemented and validated with mocks; **uncommitted**. |
| PostgreSQL / pgvector | Implemented; two separate chunk indexes. |
| Ollama embeddings | Implemented in the Flowise path only. |
| Private Llama on vLLM | Configuration targets only; local dev uses Ollama. |
| Temenos banking APIs | **Conceptual** — prompt text only. |
| Keycloak / SSO / RBAC | **Conceptual.** |
| Durable workflow engine | **Conceptual.** |
| OpenStack Kubernetes | **Conceptual.** |
| GitLab CI/CD, AWS SageMaker | **Conceptual.** |
| MLOps data-export approval | **Conceptual.** |

## 7. Implications for the plan

- The Agentflow V2 work should be committed (by its owner) before refactoring, because the upgrade builds on it.
- Authentication and tenant isolation cannot be bolted on later without touching every query; the `tenant_id` column and an authorization dependency should land in the same migration series as the Alembic baseline.
- One RAG index must become the system of record so that access control is enforced in one place. The FastAPI-owned `document_chunks` index is the right choice: the Agentflow already retrieves through `/retrieval/query`. The embedding dimension (1536 for the hash/OpenAI path, 768 for `embeddinggemma`) must be resolved in a migration.
- Existing unversioned routes are consumed by LISA, Streamlit and both Flowise flows. They must stay working, behind compatibility adapters, while `/api/v1` is introduced.

See `docs/IMPLEMENTATION_PLAN.md` for the prioritized work.
