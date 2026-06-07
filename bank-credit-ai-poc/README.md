# Bank Credit AI POC

A banking credit scoring assistant proof of concept for loan officers. The app creates customer profiles, uploads customer credit documents, ingests and embeds document chunks into PostgreSQL with pgvector, and answers credit-risk questions with citations through a RAG workflow.

This is a credit decision-support assistant, not an automatic loan approval system. It must never claim that a loan is approved or rejected automatically. Every AI credit assessment is required to include:

- Human credit officer review required
- Citations from retrieved documents
- Risk factors
- Missing information
- Confidence level
- Limitations

## Architecture

```text
Loan Officer
  |
  v
Streamlit UI :8501
  |
  v
FastAPI Backend :8000
  |       |          |
  |       |          +--> Flowise :3000 optional orchestration
  |       +-------------> OpenAI or DeepSeek LLM
  +---------------------> PostgreSQL + pgvector :5432
                            |
                            +--> customers, documents, chunks, chat, assessments, audit_logs
```

## Project Structure

```text
bank-credit-ai-poc/
  README.md
  .env.example
  docker-compose.yml
  backend/
  frontend/
  db/
  flowise/
```

## Setup

1. Copy the environment file:

```bash
cp .env.example .env
```

2. Add at least `OPENAI_API_KEY` to `.env`.

3. Start the stack:

```bash
docker compose up --build
```

By default, the Docker stack starts PostgreSQL, FastAPI, and Streamlit. Flowise is optional because the Flowise image is large and can be slow or unstable to pull on some WSL/Docker Desktop setups.

To include Flowise with Docker, this POC pins `flowiseai/flowise:3.1.2`:

```bash
docker compose --profile flowise up --build
```

From the root launcher:

```bash
./start.sh                         # Skip Docker Flowise by default
START_DOCKER_FLOWISE=1 ./start.sh  # Include Docker Flowise
```

The non-Docker local launcher uses `npx --yes flowise@3.1.2 start` when no global `flowise` command is installed.

## Local Setup Without Docker

From the repository root, use:

```bash
cd /home/dzoan/docfactorFlowise
chmod +x start-local.sh
./start-local.sh
```

`start-local.sh` runs the stack from local installs instead of Docker:

- Installs PostgreSQL + pgvector with `apt` if missing
- Creates the `credit_ai` database and `credit_ai_user`
- Applies `db/init.sql`
- Creates Python virtual environments for backend and frontend
- Installs `backend/requirements.txt` and `frontend/requirements.txt`
- Starts FastAPI on `http://localhost:8000`
- Starts Streamlit on `http://localhost:8501`
- Starts Flowise on `http://localhost:3000` if `flowise` or `npx` is available
- Starts the launcher on `http://localhost:8080`

Useful options:

```bash
INSTALL_POSTGRES=0 ./start-local.sh   # Skip apt install if PostgreSQL is already installed
START_FLOWISE=0 ./start-local.sh      # Skip Flowise
OPEN_BROWSER=1 ./start-local.sh       # Open launcher in browser
```

For Local Mistral via Ollama, Ollama still runs as a separate local service:

```bash
ollama serve
ollama pull mistral:7b-instruct
```

## URLs

- Backend Swagger: http://localhost:8000/docs
- Streamlit UI: http://localhost:8501
- Flowise: http://localhost:3000
- PostgreSQL: localhost:5432

## Environment

```env
DATABASE_URL=postgresql+psycopg2://credit_ai_user:credit_ai_password@postgres:5432/credit_ai
OPENAI_API_KEY=
DEEPSEEK_API_KEY=
LLM_PROVIDER=openai
OPENAI_MODEL=gpt-4o-mini
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
EMBEDDING_MODEL=text-embedding-3-small
CUSTOM_PUBLIC_API_BASE_URL=
CUSTOM_PUBLIC_API_KEY=
CUSTOM_PUBLIC_API_MODEL=
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=mistral:7b-instruct
DEV_ALLOW_INSECURE_CUSTOM_API=false
FLOWISE_API_URL=http://flowise:3000
FLOWISE_CHATFLOW_ID=
BACKEND_URL=http://backend:8000
```

Use `LLM_PROVIDER=deepseek` with `DEEPSEEK_API_KEY` to call DeepSeek through its OpenAI-compatible API.

## LLM Provider Modes

The Streamlit sidebar exposes exactly four provider options:

1. OpenAI
2. DeepSeek
3. Custom Public API
4. Local Mistral via Ollama

Internal provider values are `openai`, `deepseek`, `custom_public_api`, and `local_mistral_ollama`.

### OpenAI

Uses:

```env
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```

### DeepSeek

Uses:

```env
DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

### Custom Public API

The user enters a base URL, API key, and model name at runtime. This supports public OpenAI-compatible `/v1/chat/completions` providers.

Examples:

```text
Mistral API
Base URL: https://api.mistral.ai/v1
Model: mistral-small-latest

Together AI
Base URL: https://api.together.xyz/v1
Model: meta-llama/Llama-3.3-70B-Instruct-Turbo

Groq
Base URL: https://api.groq.com/openai/v1
Model: llama-3.1-8b-instant

OpenRouter
Base URL: https://openrouter.ai/api/v1
Model: mistralai/mistral-small-3.1-24b-instruct

Fireworks
Base URL: https://api.fireworks.ai/inference/v1
Model: accounts/fireworks/models/llama-v3p1-8b-instruct
```

Runtime values take precedence over `.env` values:

```env
CUSTOM_PUBLIC_API_BASE_URL=
CUSTOM_PUBLIC_API_KEY=
CUSTOM_PUBLIC_API_MODEL=
```

Public custom API URLs must use `https://`. For local development only, `http://` can be enabled with:

```env
DEV_ALLOW_INSECURE_CUSTOM_API=true
```

### Local Mistral Via Ollama

Install Ollama, then run:

```bash
ollama pull mistral:7b-instruct
ollama serve
```

If the backend runs in Docker:

```env
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

If the backend runs locally:

```env
OLLAMA_BASE_URL=http://localhost:11434
```

Security notes:

- Do not log API keys.
- Do not store custom API keys.
- Do not send custom API keys to Flowise unless using secure Flowise credentials.
- For production, use a secrets manager such as AWS Secrets Manager, Vault, or environment-managed credentials.

## Example Workflow

1. Open Streamlit at http://localhost:8501.
2. Create a customer profile with name, customer type, industry, and country.
3. Upload customer documents such as PDFs, TXT files, CSVs, or XLSX workbooks.
4. Select uploaded documents and click `Ingest selected documents`.
5. Ask questions in the chat.
6. Generate a standard credit assessment.
7. Review citations, risk factors, missing information, confidence, and limitations.
8. A human credit officer makes the actual decision outside this POC.

## Example Questions

- Summarize this customer's credit risk.
- What are the main financial weaknesses in the uploaded documents?
- Is there evidence of overdue debt or default?
- What documents are missing for a complete credit review?
- Compare this customer against the bank credit policy.
- Give me a preliminary risk level with citations.
- Which financial indicators should a human credit officer review?

## API Summary

- `POST /customers`
- `GET /customers`
- `GET /customers/{customer_id}`
- `POST /documents/upload`
- `GET /documents?customer_id={customer_id}`
- `POST /ingest/{document_id}`
- `GET /retrieval/{customer_id}?question=...&top_k=8`
- `POST /chat`
- `POST /credit-assessment/{customer_id}`
- `GET /health`

## RAG Behavior

Documents are parsed with PyMuPDF, optional pdfplumber table extraction, pandas, and openpyxl. Text is chunked into roughly 3000-character chunks with overlap. Chunks are embedded with OpenAI `text-embedding-3-small` by default and stored in `document_chunks.embedding vector(1536)`.

The fastest POC path is to let FastAPI own retrieval and use Flowise mainly as the prompt/model orchestration layer. FastAPI receives `customer_id` and the question, embeds the question, retrieves top chunks from pgvector, sends the question and context to Flowise, then returns the answer plus backend-generated citations.

```text
POST /chat
   |
   v
FastAPI receives customer_id + question
   |
   v
FastAPI embeds question
   |
   v
FastAPI retrieves top chunks from pgvector
   |
   v
FastAPI sends question + context to Flowise
   |
   v
Flowise calls OpenAI or DeepSeek
   |
   v
FastAPI returns answer + citations
```

If Flowise is not configured, or if Flowise fails, the backend can call the LLM directly.

## Document Source Connectors

FastAPI owns connector logic, security, ingestion, audit, and document metadata. The frontend only collects source configuration and calls FastAPI. Flowise does not directly connect to bank document stores.

Available now:

- Manual Upload
- S3 / S3-compatible storage

Prepared placeholder connectors:

- SharePoint via Microsoft Graph API
- OpenText via REST API or CMIS
- Hyland via OnBase APIs/vendor SDK
- IBM FileNet via FileNet API/CMIS/vendor SDK
- ServiceNow via REST + Attachment API
- Salesforce via ContentDocument/ContentVersion API
- Cloud Storage via Azure Blob, Google Cloud Storage, MinIO, or other APIs

The Streamlit UI includes a `Data Store Source` dropdown with:

- Manual Upload
- S3
- SharePoint
- OpenText
- Hyland
- FileNet
- ServiceNow
- Salesforce
- Cloud Storage

S3 imports store document metadata in `documents.source_type`, `documents.source_uri`, `documents.external_document_id`, and `documents.source_metadata`.

Example MinIO / S3-compatible config:

```text
Endpoint URL: http://localhost:9000
Access Key ID: minioadmin
Secret Access Key: minioadmin
Region: us-east-1
Bucket: credit-documents
Prefix: poc/
```

AWS S3 note: if running in AWS, prefer IAM role or profile credentials over static keys.

Connector security notes:

- Use read-only credentials for document connectors.
- Do not store API keys or secrets in audit logs.
- Preserve source metadata.
- Enforce user permissions before retrieval.
- For production, integrate with bank IAM/SSO and document-level ACLs.
- Keep original files for audit and reprocessing.
- Avoid connecting directly to production repositories during early POC; use anonymized exports or read-only test repositories.

## Safety Guardrails

The LLM system prompt enforces:

- Banking credit analysis assistant role
- Decision support only
- No automatic approval or rejection
- Use only provided context
- Missing evidence must be stated
- Citations using document name and page number
- Confidence level and limitations
- No hallucination
- Sensitive data minimization
- Structured answer sections
- Human credit officer review required

The rule-based helper in `credit_scoring.py` is deliberately labeled as a preliminary heuristic, not a final credit score.

## Limitations

- No production authentication or authorization
- No real policy-document governance yet
- No automated RAG evaluation
- No citation quality scoring
- No PII masking beyond prompt instructions
- No human approval workflow
- No data retention automation
- Flowise export is a documented placeholder, not a guaranteed importable flow

## Production Hardening Checklist

- Real authentication with Cognito, Keycloak, or Azure AD
- Role-based access control
- Customer-level data isolation
- Encryption at rest and in transit
- PII detection and masking
- Data residency controls
- Human approval workflow
- Model/prompt versioning
- RAG evaluation with golden dataset
- Citation accuracy evaluation
- Monitoring with CloudWatch/Prometheus/Grafana
- Cost tracking per customer/request
- Backup and retention policy
- No automatic loan approval
- Legal/compliance review
