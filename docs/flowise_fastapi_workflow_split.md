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

| Order | Stage / Element | Owner | Task | Relationship |
| --- | --- | --- | --- | --- |
| 1 | `chat_input` | Flowise | Receives the user question. | Sends raw question to `runtime_vars`. |
| 2 | `runtime_vars` | Flowise | Normalizes `customer_id`, `session_id`, `user_id`, `language`, `llm_provider`, `llm_model`, `policy_mode`, and `question`. | Feeds document upload, prompt, and LLM router. |
| 3 | `document_upload` | FastAPI via Flowise | Represents `POST /documents/upload` with customer/session/source/file metadata. | Routes to `document_status`. |
| 4 | `document_status` | FastAPI via Flowise | Represents `GET /documents/{document_id}/status`. | Routes backend ingestion state to parser/checkpoint visuals. |
| 5 | `parser` | FastAPI | Tracks parse status. | Receives status from `document_status`, routes to `chunker`. |
| 6 | `chunker` | FastAPI | Tracks chunking status. | Routes to `embeddings`. |
| 7 | `embeddings` | FastAPI | Tracks embedding generation status. | Routes to `postgresql`. |
| 8 | `postgresql` | FastAPI | Tracks document/chunk persistence. | Routes to `pgvector`. |
| 9 | `pgvector` | FastAPI | Tracks vector index readiness. | Routes to retrieval call. |
| 10 | `http_retrieval_tool` | FastAPI via Flowise | Represents `POST /retrieval/query`. | Sends customer/session/question/top_k/filters to backend retrieval. |
| 11 | `retriever` | FastAPI | Displays retrieved evidence count and retrieval status. | Routes to citation builder. |
| 12 | `citation_builder` | Flowise | Converts backend evidence into citation objects and citation text. | Feeds prompt and loan policy scoring. |
| 13 | `loan_policy_scoring` | FastAPI via Flowise | Represents `POST /loan-policy/score`. | Feeds DTI, LTV, rate, payment, and recommendation visual nodes. |
| 14 | `dti` | FastAPI | Displays DTI result from policy scoring. | Feeds recommendation. |
| 15 | `ltv` | FastAPI | Displays LTV result from policy scoring. | Feeds recommendation. |
| 16 | `interest_rate` | FastAPI | Displays selected/calculated interest rate. | Feeds monthly payment. |
| 17 | `monthly_payment` | FastAPI | Displays estimated monthly payment. | Feeds recommendation. |
| 18 | `recommendation` | FastAPI | Displays policy recommendation and breaches. | Feeds prompt. |
| 19 | `prompt_template` | Flowise | Builds LISA prompt from evidence, citations, policy score, runtime vars, and human-review rule. | Feeds LLM chain. |
| 20 | `llm_router` | Flowise | Selects one provider from runtime variables. | Routes to provider options. |
| 21 | `ollama_mistral` | Flowise | Ollama provider option. | Feeds LLM chain only when selected. |
| 22 | `ollama_gemma` | Flowise | Ollama local model option using runtime `llm_model`. | Feeds LLM chain only when selected. |
| 23 | `openai_provider` | Flowise | OpenAI provider option using environment credentials. | Feeds LLM chain only when selected. |
| 24 | `deepseek_provider` | Flowise | DeepSeek provider option using environment credentials. | Feeds LLM chain only when selected. |
| 25 | `custom_provider` | Flowise | Custom provider option using environment configuration. | Feeds LLM chain only when selected. |
| 26 | `llm_chain` | Flowise | Runs the selected LLM against the LISA prompt. | Routes answer to parser. |
| 27 | `output_parser` | Flowise | Shapes raw LLM output into the expected decision-support sections. | Routes to credit assessment. |
| 28 | `credit_assessment` | Flowise | Marks answer as decision support and human-review required. | Routes to committee stage. |
| 29 | `approval_committee` | FastAPI via Flowise | Represents committee case submission. | Routes to final decision. |
| 30 | `final_decision` | FastAPI via Flowise | Records human decision only; LLM cannot make final decision. | Routes to email draft. |
| 31 | `customer_email_draft` | FastAPI via Flowise | Drafts customer notification from the decision state. | Routes to audit logging. |
| 32 | `audit_logging` | FastAPI via Flowise | Represents `POST /audit`. | Routes to final chat output after logging. |
| 33 | `chat_output` | Flowise | Displays answer to user. | Terminal stage. |

## Backend Compatibility Notes

The FastAPI compatibility layer accepts Flowise string customer identifiers such as `demo_customer` and maps them to backend customer records. Numeric customer IDs continue to resolve to existing database customers.

Document IDs returned to Flowise include an external `doc_<id>` value while preserving the original backend `id` field.

Final decisions require a human `decided_by` or `decision_by` value. Missing human decision ownership is rejected.
