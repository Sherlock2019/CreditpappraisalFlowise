# HyperSpeed Banking AI Copilot

Ultra fast and reliable credit appraisal workspace powered by a focused credit-review UI, FastAPI, PostgreSQL/pgvector, Flowise, and local/public LLM routing.

The default app is the single credit appraisal page:

`http://127.0.0.1:8080`

It is designed for a loan officer workflow: create/select customers, upload credit documents, ingest evidence, ask LISA questions, score policy risk, prepare committee review, record final decision, draft customer email, and retain audit evidence.

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
cd /home/dzoan/docfactorFlowise
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
