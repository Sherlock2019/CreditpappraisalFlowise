# Flowise / FastAPI Credit Appraisal Workflow Split

Live Flowise ID: `6f946e8b-2d35-4fd4-9ff9-158db1f0b820`

Live exported graph files:

- `flowise_project/generated/live-flowise-flowdata-from-db.json`
- `flowise_project/generated/live-flowise-ui-import-from-db.json`
- `flowise_project/generated/live-flowise-api-import-from-db.json`

## Ownership Rules

Flowise owns the visual workflow, stage orchestration, runtime variable routing, prompt template, selected LLM provider, LLM response, output parser, and final chat output.

FastAPI owns document upload, document status, storage, parsing, chunking, embeddings, PostgreSQL/pgvector retrieval, evidence formatting, loan policy scoring, committee submission, final human decision recording, customer email draft, and audit logging.

The workflow is decision support only. It must preserve this rule in the prompt and output:

`Human credit officer review required.`

## Runtime LLM Routing

The old sequential provider chain was removed:

`Ollama -> OpenAI -> DeepSeek -> Custom API`

The live graph now uses a single selectable provider route:

`runtime_vars -> llm_router -> selected provider option -> llm_chain`

Runtime variables:

| Variable | Purpose |
| --- | --- |
| `customer_id` | Selected customer, or a Flowise session customer identifier. |
| `session_id` | Chat/session correlation ID used by FastAPI and audit. |
| `user_id` | Operator/auditor identifier. |
| `language` | Response language hint. |
| `llm_provider` | Provider route: `ollama`, `openai`, `deepseek`, or `custom`. |
| `llm_model` | Selected model, for example `mistral` or `gemma2:9b`. |
| `policy_mode` | Policy/scoring profile passed to FastAPI. |
| `question` | User question sent to retrieval and LISA. |

## Required FastAPI Endpoints

| Endpoint | Method | Owner | Purpose |
| --- | --- | --- | --- |
| `/documents/upload` | `POST` | FastAPI | Accept file upload and metadata from Flowise. |
| `/documents/{document_id}/status` | `GET` | FastAPI | Return parser, chunker, embeddings, PostgreSQL, and pgvector status. |
| `/retrieval/query` | `POST` | FastAPI | Retrieve customer evidence chunks with citations. |
| `/loan-policy/score` | `POST` | FastAPI | Calculate policy score, DTI, LTV, rate, monthly payment, breaches, and recommendation. |
| `/approval-committee/submit` | `POST` | FastAPI | Create a human committee case. |
| `/final-decision` | `POST` | FastAPI | Record human final decision only. |
| `/customer-decision-email/draft` | `POST` | FastAPI | Draft customer notification from recorded decision state. |
| `/audit` | `POST` | FastAPI | Log workflow question, evidence IDs, selected model, policy score, answer, and human review flag. |

## Workflow Stage Table

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

## Backend Compatibility Notes

The FastAPI compatibility layer accepts Flowise string customer identifiers such as `demo_customer` and maps them to backend customer records. Numeric customer IDs continue to resolve to existing database customers.

Document IDs returned to Flowise include an external `doc_<id>` value while preserving the original backend `id` field.

Final decisions require a human `decided_by` or `decision_by` value. Missing human decision ownership is rejected.
