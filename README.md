# HyperSpeed Banking AI Copilot

Ultra fast and reliable credit appraisal workspace powered by a focused credit-review UI, FastAPI, PostgreSQL/pgvector, Flowise, and local/public LLM routing.

The default app is the single credit appraisal page:

`http://127.0.0.1:8080`

It is designed for a loan officer workflow: create/select customers, upload credit documents, ingest evidence, ask LISA questions, score policy risk, prepare committee review, record final decision, draft customer email, and retain audit evidence.

## Project Status

This is a local proof of concept. It is not production-ready.

- **Governed agent path (new, `/api/v1`).** Requires a bearer token. People use OIDC tokens; each Flowise agent gets its own short-lived token for one run. Access is checked per tenant and per role, and every tool call is audited. Credit decisions can only be recorded by a second, authenticated officer. See [`docs/FLOWISE_INTEGRATION.md`](docs/FLOWISE_INTEGRATION.md).
- **Legacy LISA/Streamlit routes stay anonymous** in local dev (`LEGACY_AUTH_MODE=dev-anonymous`). `/chat` and `/final-decision` already respect tenants and reject agent tokens. Run the app only on a trusted machine.
- **Not implemented yet:** Temenos, a Keycloak realm, the React console, Temporal, Alembic migrations, OpenTelemetry/Prometheus, Kubernetes, CI/CD and SageMaker.

| Document | Contents |
| --- | --- |
| [`docs/IMPLEMENTATION_GAP_ANALYSIS.md`](docs/IMPLEMENTATION_GAP_ANALYSIS.md) | What exists, what is tested, what is missing, and the critical security findings |
| [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) | Prioritized milestones (M0–M11), acceptance tests, and open decisions |
| [`docs/FLOWISE_INTEGRATION.md`](docs/FLOWISE_INTEGRATION.md) | How the Agentflow and Chatflow use identities, approval, tenants and audit |
| [`docs/AGENT_PERMISSIONS.md`](docs/AGENT_PERMISSIONS.md) | Agent tool scopes and human role permissions |

## Platform Demo

[`scripts/demo_platform.py`](scripts/demo_platform.py) runs every stage of the Flowise "Enterprise Platform" lane through FastAPI and prints PASS/FAIL per stage. Planned stages are listed, not faked.

```bash
# Offline: the real FastAPI app in-process on SQLite, a simulated Agentflow, evidence parsed from the
# synthetic CUST-001 documents. Needs no Postgres, Flowise or LLM.
.venv/bin/python scripts/demo_platform.py

# Live: against a backend started with AUTH_DEV_MODE=true and the same AUTH_DEV_JWT_SECRET,
# which calls the real Flowise Agentflow.
AUTH_DEV_JWT_SECRET=... .venv/bin/python scripts/demo_platform.py --live --api http://127.0.0.1:8000 --customer 2
```

The demo checks: SSO token validation, tenant isolation and RBAC, per-agent credentials, typed API errors and idempotency, the agent run pausing at the approval gate, refusals of cross-agent and injected-customer calls, four-eyes approval and resume, correlation ids, the audit hash chain and its tamper detection, document and spreadsheet parsing, connectors, and the Agentflow validator.

## Skills Evidence Map

Where each skill shows up in this repository, and how it is verified.

**Status:** **Shown** means code plus passing automated tests. **Partial** means code exists but is incomplete or untested. **Not shown** means there is no code for it yet (see the plan). **Not provable from code** covers skills a repository cannot evidence.

Verification commands: `.venv/bin/python -m pytest tests -q` (35 tests) and `node flowise_project/agentflows/validate-agentflows.js` (9 scenarios × 3 environments).

### Primary skills: full-stack engineering

| Skill | Status | Where to look | Verified by |
| --- | --- | --- | --- |
| Python, FastAPI, Pydantic | Shown | [`routers/v1/`](bank-credit-ai-poc/backend/app/routers/v1/), [`schemas_v1.py`](bank-credit-ai-poc/backend/app/schemas_v1.py), [`auth/dependencies.py`](bank-credit-ai-poc/backend/app/auth/dependencies.py) | [`tests/test_agent_gateway.py`](tests/test_agent_gateway.py) |
| Typed API design | Shown | Strict Pydantic models (`extra="forbid"`, `Literal` enums, bounds); one error envelope with correlation id ([`errors.py`](bank-credit-ai-poc/backend/app/errors.py)); OpenAPI at `/docs`; tool contracts exported to [`tool-schemas.json`](flowise_project/agentflows/tool-schemas.json) | [`tests/test_tool_schemas.py`](tests/test_tool_schemas.py) (fails on schema drift) |
| PostgreSQL and data modeling | Partial | [`models.py`](bank-credit-ai-poc/backend/app/models.py) (runs, approvals, hash-chained audit, pgvector chunks, JSONB); tenant-scoped pgvector SQL in [`rag.py`](bank-credit-ai-poc/backend/app/rag.py); per-tenant advisory lock in [`audit_chain.py`](bank-credit-ai-poc/backend/app/services/audit_chain.py) | API tests run on SQLite; no Alembic migrations yet |
| Distributed and asynchronous systems | Partial | FastAPI ↔ Flowise callback protocol with pause/resume ([`agent_runtime.py`](bank-credit-ai-poc/backend/app/services/agent_runtime.py)), idempotency keys, retries with exponential backoff, correlation ids across services | Gateway tests; no durable workflow engine or queue yet |
| TypeScript, React | Not shown | The LISA UI is vanilla JS ([`creditappflowise/`](creditappflowise/)); React console is milestone M2 | none |
| End-to-end feature delivery | Shown (backend + AI flow) | Governed agent runs: gap analysis → design → API → Flowise flows → tests → docs, in branch history | Tests, validator, live run notes in [`docs/FLOWISE_INTEGRATION.md`](docs/FLOWISE_INTEGRATION.md) |

### Primary skills: AI and data

| Skill | Status | Where to look | Verified by |
| --- | --- | --- | --- |
| LLM agents and tool calling | Shown | Agentflow V2 generator with router, 4 specialists, memo agent and structured outputs ([`build-agentflows.js`](flowise_project/agentflows/build-agentflows.js)); typed tool gateway ([`routers/v1/tools.py`](bank-credit-ai-poc/backend/app/routers/v1/tools.py)) | Validator dry runs; gateway tests with a simulated flow; live run (see the limitations in FLOWISE_INTEGRATION) |
| MCP | Partial | MCP-style typed tool schemas and scope-filtered manifest (`GET /api/v1/tools/manifest`); no MCP transport server | `test_human_token_cannot_call_tools_and_manifest_is_scope_filtered` |
| AI evaluation | Partial | Staging Evaluation Judge node (groundedness, citation coverage, policy consistency) in the AWS staging flow; adversarial validator scenarios (hallucinated recommendation, Proceed without a decision) | Validator; no versioned eval dataset or metrics pipeline yet |
| Data pipelines | Partial | Upload → parse → chunk → embed → pgvector ([`routers/documents.py`](bank-credit-ai-poc/backend/app/routers/documents.py), [`document_parser.py`](bank-credit-ai-poc/backend/app/document_parser.py)); Flowise vector upsert ([`ensure-flowise-flows.js`](scripts/ensure-flowise-flows.js)) | Runs inline, not durable; parsers untested |
| Knowledge graphs and ontology | Not shown | none | none |
| Spreadsheet and document processing | Partial | PDF, DOCX, XLSX, CSV and image parsing in [`document_parser.py`](bank-credit-ai-poc/backend/app/document_parser.py); synthetic dataset in [`docfactor_banking_demo_dataset/`](docfactor_banking_demo_dataset/) | No parser tests yet |

### Primary skills: integrations and security

| Skill | Status | Where to look | Verified by |
| --- | --- | --- | --- |
| Enterprise APIs and SaaS integrations | Partial | Connector interface; S3 is a real connector; SharePoint, Salesforce, ServiceNow, OpenText, Hyland and FileNet are placeholders ([`connectors/`](bank-credit-ai-poc/backend/app/connectors/)); Flowise prediction and resume API client | No connector tests; Temenos is not implemented |
| OAuth 2.0 / SSO | Partial | OIDC token validation: JWKS (RS256/ES256), issuer, audience, expiry, tenant claim, Keycloak roles ([`auth/tokens.py`](bank-credit-ai-poc/backend/app/auth/tokens.py)) | Forged, expired and wrong-audience tokens rejected in `test_v1_requires_a_valid_token`; no Keycloak realm or PKCE browser flow yet |
| SCIM | Not shown | none | none |
| Secure credential handling | Shown | Short-lived agent tokens bound to one run, never in prompts; secrets only from env; redaction in audit; `.env` git-ignored | Validator rule "token outside Authorization header"; `test_tools_are_disabled_while_the_run_waits_for_a_human` |
| Multi-tenant authorization, RBAC, audit | Shown | Default-deny role map ([`auth/policy.py`](bank-credit-ai-poc/backend/app/auth/policy.py)); per-agent scopes ([`agent_permissions.json`](bank-credit-ai-poc/backend/app/auth/agent_permissions.json)); tenant filtering; four-eyes approval; hash-chained audit with verification | `test_other_tenant_cannot_see_or_act_on_demo_data`, `test_agent_cannot_use_another_agents_evidence_domain`, `test_editing_an_audit_row_breaks_the_chain` |

### Primary skills: cloud and reliability

| Skill | Status | Where to look | Verified by |
| --- | --- | --- | --- |
| Docker | Partial | Backend and Streamlit Dockerfiles; [`docker-compose.yml`](bank-credit-ai-poc/docker-compose.yml) with pgvector and Flowise | Not built in CI |
| GCP | Not shown | none (an AWS staging profile exists only as configuration) | none |
| CI/CD | Not shown | The suites above are CI-ready; no pipeline file yet | none |
| Temporal or similar | Not shown | The Flowise pause/resume is coordinated by FastAPI, which is not a durable engine (milestone M6) | none |
| Automated testing | Shown | 35 pytest tests; Agentflow validator with schema checks and security rules | The validator rejects deliberately broken flows (wrong agent token, legacy decision call, token in a prompt) |
| Observability and troubleshooting | Partial | Correlation ids on every request, Flowise call and audit event; structured error envelope; queryable audit API | No OpenTelemetry, Prometheus or Grafana yet |

### Secondary skills

| Skill | Status | Where to look |
| --- | --- | --- |
| Hands-on cloud (GCP/AWS/Azure) | Not shown | Configuration targets only (AWS staging and OpenStack production Agentflow profiles, S3 connector) |
| MLOps: Docker, Kubernetes, MLflow | Partial (Docker only) | No Kubernetes or MLflow |
| Running self-hosted LLMs | Shown locally | Ollama (gemma4, mistral, embeddinggemma) behind Flowise and FastAPI; vLLM endpoints configured for production and staging but not deployed |
| Fine-tuning LLMs on cloud GPUs | Not shown | none |
| Automated evaluation: grounding, hallucination, drift | Partial | Evaluation Judge node; no drift analysis |
| Deploying AI with monitoring and guardrails | Partial | Guardrails: prompt rules, moderation deny-list, tool-boundary authorization, human approval gate. No deployment or monitoring stack |

### Professional skills

| Skill | Status | Evidence |
| --- | --- | --- |
| System design and problem-solving | Partial | [`docs/IMPLEMENTATION_GAP_ANALYSIS.md`](docs/IMPLEMENTATION_GAP_ANALYSIS.md), [`docs/FLOWISE_INTEGRATION.md`](docs/FLOWISE_INTEGRATION.md) (ownership split, threat-driven controls) |
| Clear technical communication | Partial | The docs above, commit history, and this map |
| End-to-end ownership | Partial | The branch history shows a feature taken from audit to tested delivery. Production ownership cannot be shown by a repository |
| Cross-functional collaboration | Not provable from code | none |
| Mentoring and technical leadership | Not provable from code | none |

## What This Runs

| Layer | Purpose | Default URL |
| --- | --- | --- |
| Credit Appraisal UI | Main browser app, served from `creditappflowise/` | `http://127.0.0.1:8080` |
| FastAPI backend | Customers, uploads, ingestion, retrieval, policy scoring, workflow records | `http://127.0.0.1:8000` |
| FastAPI Swagger | API explorer | `http://127.0.0.1:8000/docs` |
| Flowise UI | Visual LISA orchestration workflow | `http://127.0.0.1:3001` |
| PostgreSQL/pgvector | Customer/document/chunk/vector storage | `127.0.0.1:5432` |
| Streamlit legacy UI | Older proof-of-concept UI | `http://127.0.0.1:8501` |

## Quick Start

Run everything from WSL/Ubuntu:

```bash
cd CreditpappraisalFlowise
./start.sh
```

`start.sh` now installs Python packages from:

- `bank-credit-ai-poc/backend/requirements.txt`
- `bank-credit-ai-poc/frontend/requirements.txt`

The install happens inside a local `.venv/` and is skipped on later starts until either requirements file changes.

On startup, the launcher also preloads the demo customer document dataset from:

`docfactor_banking_demo_dataset/customer_documents`

This registers the `CUST-001` through `CUST-015` files in FastAPI so the customer dropdown and document table are populated immediately.

Common launcher options:

```bash
# Skip Python package install
INSTALL_REQUIREMENTS=0 ./start.sh

# Restart local Flowise before opening the app
RESTART_LOCAL_FLOWISE=1 ./start.sh

# Skip Docker stack if services are already running
START_STACK=0 ./start.sh

# Start Docker Flowise profile instead of local Flowise
START_DOCKER_FLOWISE=1 ./start.sh

# Do not open FastAPI Swagger automatically
OPEN_FASTAPI=0 ./start.sh

# Skip demo customer document preload
PRELOAD_DEMO_DATASET=0 ./start.sh
```

The old full dashboard can still be launched with:

```bash
./startallagent.sh
```

## Main Page

The main UI is intentionally focused on credit appraisal only.

Important files:

| File | Purpose |
| --- | --- |
| `creditappflowise/index.html` | Main credit appraisal page |
| `creditappflowise/docfactor-ui.js` | App logic, uploads, customers, chat, workflow actions |
| `creditappflowise/docfactor-ui.css` | Main UI styling and light/dark theme |
| `creditappflowise/jarvis_british_speak.js` | Browser voice support |
| `web_proxy.py` | Static UI server plus `/api` proxy to FastAPI |
| `start.sh` | Primary launcher |
| `startallagent.sh` | Legacy full-dashboard launcher |

## Document Uploads And Customer Parsing

The app ships with a demo dataset:

`docfactor_banking_demo_dataset/customer_documents`

Each customer folder contains synthetic financial statements, bank statements, tax summaries, loan applications, and collateral valuations. `./start.sh` mounts this folder read-only into the backend container and calls:

`POST /documents/preload-demo-dataset`

That endpoint copies supported files into the backend upload store, creates missing demo customers, and upserts document rows.

The upload flow supports both individual files and folder uploads. Folder uploads preserve browser-relative paths and the UI parses customer codes from names like:

```text
customer_documents/CUST-011/CUST-011_tax_return_summary.pdf
```

Expected behavior:

1. Select `All customers - general questions` or a specific customer.
2. Choose files or a folder.
3. The UI dry-runs the upload routes before sending.
4. Files containing `CUST-###` are routed to that parsed customer code.
5. FastAPI creates or finds the customer.
6. If auto-ingest is enabled, the backend parses text and can rename generic `CUST-###` customers to borrower names found in the documents.
7. The customer dropdown reloads from `/customers` after upload.

Supported file types:

`pdf`, `txt`, `csv`, `xlsx`, `xls`, `docx`, `png`, `jpg`, `jpeg`

The backend upload router is:

`bank-credit-ai-poc/backend/app/routers/documents.py`

## LISA

LISA is the visible loan insight analyst in the app:

`ASK LISA - Your Ultra-Smart Loan Insight Analyst`

LISA can answer customer-specific or all-customer questions using retrieved document evidence. Voice mode can read the submitted question and the answer when supported by the browser.

LLM provider options are wired through the UI and backend:

| Provider | Role |
| --- | --- |
| Local Ollama | Default local model route |
| OpenAI | Public model route when configured |
| DeepSeek | Public/provider route when configured |
| Custom API | OpenAI-compatible endpoint route |

Ollama is expected at:

`http://127.0.0.1:11434`

## Real Flowise Backend

The real local Flowise UI is:

`http://127.0.0.1:3001`

The live Flowise chatflow ID is:

`6f946e8b-2d35-4fd4-9ff9-158db1f0b820`

Flowise runs from its local SQLite database:

`bank-credit-ai-poc/flowise/.flowise/database.sqlite`

That database is intentionally ignored by Git. The committed JSON exports live in:

`flowise_project/generated/`

Useful Flowise files:

| File | Purpose |
| --- | --- |
| `flowise_project/generated/live-flowise-flowdata-from-db.json` | Raw Flowise `flowData` graph exported from the live DB row |
| `flowise_project/generated/live-flowise-chatflow-from-db.json` | Full chatflow-style export from the live DB row |
| `flowise_project/generated/live-flowise-ui-import-from-db.json` | UI import payload |
| `flowise_project/generated/live-flowise-api-import-from-db.json` | API import payload with stringified `flowData` |
| `flowise_project/generated/lean1617-docfactor_flowise_fastapi_chatflow.json` | Fixed generated Flowise/FastAPI workflow export |

Useful Flowise scripts:

| Script | Purpose |
| --- | --- |
| `scripts/export-live-flowise-json.js` | Export the live SQLite chatflow row to JSON |
| `scripts/import-live-flowise-json-to-db.js` | Import generated workflow JSON into the live SQLite row with a backup |
| `scripts/import-flowise-json-to-db.js` | Direct importer for a chosen generated Flowise JSON file |
| `scripts/update-live-flowise-split.js` | Regenerate the Flowise/FastAPI split graph |

Use the direct importer when Flowise UI import opens a blank flow. The UI import path can be flaky; the DB importer is the reliable path for this project.

## Workflow Ownership

Flowise should show orchestration stages. FastAPI should do secure backend work, document processing, scoring, persistence, and human-decision records.

| # | Workflow area | Should appear in Flowise? | Flowise responsibility | FastAPI responsibility | Node type in Flowise |
| -: | --- | --- | --- | --- | --- |
| 1 | Chat Input | Yes | Receive user question | N/A | Native/chat input node |
| 2 | Runtime Variables | Yes | Pass `customer_id`, `llm_provider`, `llm_model`, language, session context | Validate customer/session permissions | Custom function / variables node |
| 3 | Document Upload | Yes | Trigger/upload document from chat UI or workflow | Validate file, store file, create document record | HTTP call to `/documents/upload` |
| 4 | Parser | Yes | Show parser stage in the Flowise workflow | Extract text from PDF, DOCX, image, Excel, CSV | HTTP call / backend pipeline status node |
| 5 | Chunker | Yes | Show chunking stage in the workflow | Split text into searchable chunks | HTTP call / backend pipeline status node |
| 6 | Embeddings | Yes | Trigger embedding generation or show status | Generate embeddings, store embedding model/version | HTTP call / backend pipeline status node |
| 7 | PostgreSQL | Yes, as storage stage | Show where customer/document data is stored | Store customers, docs, chunks, audit logs, decisions | Visual/storage reference node |
| 8 | pgvector | Yes, as vector index stage | Show vector-search storage layer | Store/search embeddings inside PostgreSQL | Visual/storage reference node |
| 9 | Retrieval | Yes | Call `/retrieval/query` and receive relevant evidence | Search PostgreSQL/pgvector with customer filter | HTTP retrieval node |
| 10 | Citation Builder | Yes | Format retrieved chunks into citation-ready evidence | Return filename, page, source metadata | Custom function node |
| 11 | Prompt Template | Yes | Build final LISA prompt with evidence, policy, missing data | Optionally return policy context | Prompt template node |
| 12 | LLM Router | Yes | Select local/public model route | Store available provider config/API keys if needed | Router/custom function node |
| 13 | Ollama Local Model | Yes | Run selected local model through Flowise | Ensure Ollama service/model is running | ChatOllama node |
| 14 | OpenAI | Yes | Provider option only | Secure API key/config | Provider node |
| 15 | DeepSeek | Yes | Provider option only | Secure API key/config | Provider/custom API node |
| 16 | Custom API | Yes | OpenAI-compatible provider option | Secure endpoint/key/config | Provider/custom API node |
| 17 | LLM Chain | Yes | Execute prompt + selected model | N/A | LLM Chain node |
| 18 | Output Parser | Yes | Structure LISA response | Optionally validate JSON schema | Output parser node |

Full workflow details are documented in:

`docs/flowise_fastapi_workflow_split.md`

## Backend Capabilities

FastAPI owns the system-of-record work:

| Area | Backend responsibility |
| --- | --- |
| Customers | Create, list, recover, and update customer records |
| Documents | Upload, validate, store, dedupe, recover from disk |
| Parsing | Extract text from PDF, DOCX, Excel, CSV, images, and text |
| Chunking | Split parsed text into searchable evidence chunks |
| Embeddings | Create local hash embeddings and write vector rows |
| Retrieval | Query customer-filtered evidence through pgvector |
| Policy | DTI, LTV, rate, monthly payment, recommendation |
| Committee | Submit committee packets for human review |
| Final decision | Record human final approval, rejection, deferral, or conditions |
| Email draft | Draft customer notification while requiring human approval |
| Audit | Store audit events and trace model/evidence usage |

## Environment

Docker Compose uses:

`bank-credit-ai-poc/.env`

Example values are in:

`bank-credit-ai-poc/.env.example`

Do not commit real secrets. `.env` and local Flowise SQLite files are ignored by Git.

Important local defaults:

| Variable | Default |
| --- | --- |
| `WEB_PORT` | `8080` |
| `BACKEND_URL` | `http://127.0.0.1:8000` |
| `FLOWISE_PORT` | `3001` |
| `START_LOCAL_FLOWISE` | `1` |
| `START_DOCKER_FLOWISE` | `0` |
| `START_DOCKER_DAEMON` | `1` |
| `START_OLLAMA` | `1` |
| `INSTALL_REQUIREMENTS` | `1` |
| `PRELOAD_DEMO_DATASET` | `1` |
| `DEMO_CUSTOMER_DOCUMENTS_DIR` | `/app/demo/customer_documents` |
| `PYTHON_VENV_DIR` | `.venv` |

## Development Checks

Automated tests:

```bash
# Backend unit tests (loan policy, retrieval service, Flowise client)
.venv/bin/python -m pytest tests -q
```

Useful smoke checks:

```bash
# Frontend JavaScript syntax
.tools/node-v20.18.3-linux-x64/bin/node --check creditappflowise/docfactor-ui.js

# Backend Python syntax
python3 -m py_compile bank-credit-ai-poc/backend/app/routers/documents.py

# FastAPI health
curl -fsS http://127.0.0.1:8000/health

# Main UI served by launcher
curl -fsS http://127.0.0.1:8080/
```

## Troubleshooting

### Docker daemon is not reachable

Start Docker inside WSL:

```bash
sudo service docker start
./start.sh
```

If using Docker Desktop, enable WSL integration for the Ubuntu distro.

### Flowise UI import opens a blank flow

Use the direct DB importer instead of the Flowise UI import button:

```bash
node scripts/import-flowise-json-to-db.js flowise_project/generated/lean1617-docfactor_flowise_fastapi_chatflow.json
RESTART_LOCAL_FLOWISE=1 ./start.sh
```

### Local LLM is unreachable

Check Ollama:

```bash
curl -fsS http://127.0.0.1:11434/api/tags
ollama pull mistral
```

Then restart:

```bash
RESTART_LOCAL_FLOWISE=1 ./start.sh
```

### Browser still shows old upload behavior

Hard refresh `http://127.0.0.1:8080`. The app uses cache-busted script URLs, but Chrome can still hold older assets in some sessions.

## Human Review Rule

This system is decision support only.

Every final credit output must preserve this rule:

`Human credit officer review required.`
