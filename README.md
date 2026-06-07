# HyperSpeed Credit Appraisal Flowise

Credit appraisal proof of concept with a custom credit loan officer UI, FastAPI backend, PostgreSQL/pgvector RAG, local Flowise orchestration, and selectable LLM routing.

## Start

```bash
./start.sh
```

Main URLs:

| Service | URL |
| --- | --- |
| Credit Appraisal UI | `http://127.0.0.1:8080` |
| Backend Swagger | `http://127.0.0.1:8000/docs` |
| Flowise UI | `http://127.0.0.1:3001` |
| Streamlit legacy UI | `http://127.0.0.1:8501` |

If Flowise is already running and you need it to reload the live SQLite workflow row:

```bash
RESTART_LOCAL_FLOWISE=1 ./start.sh
```

or:

```bash
RESTART_FLOWISE=1 ./start-flowise.sh
```

## Live Flowise Workflow

Live Flowise ID:

`6f946e8b-2d35-4fd4-9ff9-158db1f0b820`

Flowise runs from the local SQLite database:

`bank-credit-ai-poc/flowise/.flowise/database.sqlite`

That database is ignored by Git. The committed exported workflow JSON files are:

| File | Purpose |
| --- | --- |
| `flowise_project/generated/live-flowise-flowdata-from-db.json` | Raw Flowise `flowData` graph exported from the live DB row. |
| `flowise_project/generated/live-flowise-chatflow-from-db.json` | Full chatflow-style export from the live DB row. |
| `flowise_project/generated/live-flowise-ui-import-from-db.json` | UI import payload. |
| `flowise_project/generated/live-flowise-api-import-from-db.json` | API import payload with stringified `flowData`. |

Utility scripts:

| Script | Purpose |
| --- | --- |
| `scripts/export-live-flowise-json.js` | Export the live Flowise SQLite row to JSON. |
| `scripts/update-live-flowise-split.js` | Regenerate the Flowise/FastAPI split graph. |
| `scripts/import-live-flowise-json-to-db.js` | Import the generated graph back into the live SQLite row, with a DB backup. |

## Workflow Ownership Table

| Order | Workflow Stage | Done By | Task |
| --- | --- | --- | --- |
| 1 | `chat_input` | Flowise | Receives the user question. |
| 2 | `runtime_vars` | Flowise | Normalizes customer, session, user, language, provider, model, policy mode, and question. |
| 3 | `document_upload` | FastAPI via Flowise | Calls `POST /documents/upload` for uploaded files and metadata. |
| 4 | `document_status` | FastAPI via Flowise | Calls `GET /documents/{document_id}/status` for ingestion status. |
| 5 | `parser` | FastAPI | Parses uploaded document content. |
| 6 | `chunker` | FastAPI | Chunks parsed document text. |
| 7 | `embeddings` | FastAPI | Generates embeddings for chunks. |
| 8 | `postgresql` | FastAPI | Stores customers, documents, chunks, audits, scores, and workflow records. |
| 9 | `pgvector` | FastAPI | Stores/searches vector embeddings. |
| 10 | `http_retrieval_tool` | FastAPI via Flowise | Calls `POST /retrieval/query`. |
| 11 | `retriever` | FastAPI | Retrieves customer evidence chunks. |
| 12 | `citation_builder` | Flowise | Converts retrieved evidence into citation text for LISA. |
| 13 | `loan_policy_scoring` | FastAPI via Flowise | Calls `POST /loan-policy/score`. |
| 14 | `dti` | FastAPI | Calculates/displays debt-to-income result. |
| 15 | `ltv` | FastAPI | Calculates/displays loan-to-value result. |
| 16 | `interest_rate` | FastAPI | Calculates/displays policy interest rate. |
| 17 | `monthly_payment` | FastAPI | Calculates/displays estimated monthly payment. |
| 18 | `recommendation` | FastAPI | Produces policy recommendation and breach summary. |
| 19 | `prompt_template` | Flowise | Builds LISA prompt from evidence, citations, policy score, and runtime variables. |
| 20 | `llm_router` | Flowise | Selects one provider route from `llm_provider` and `llm_model`. |
| 21 | `ollama_mistral` | Flowise | Ollama provider option. |
| 22 | `ollama_gemma` | Flowise | Ollama local model option. |
| 23 | `openai_provider` | Flowise | OpenAI provider option. |
| 24 | `deepseek_provider` | Flowise | DeepSeek provider option. |
| 25 | `custom_provider` | Flowise | Custom provider option. |
| 26 | `llm_chain` | Flowise | Runs the selected LLM against the LISA prompt. |
| 27 | `output_parser` | Flowise | Shapes the raw LLM answer into the expected credit-review sections. |
| 28 | `credit_assessment` | Flowise | Marks the result as decision support only. |
| 29 | `approval_committee` | FastAPI via Flowise | Calls the committee submission stage. |
| 30 | `final_decision` | FastAPI via Flowise | Records human final decision only. |
| 31 | `customer_email_draft` | FastAPI via Flowise | Drafts customer-facing email from decision state. |
| 32 | `audit_logging` | FastAPI via Flowise | Calls `POST /audit` with question, evidence IDs, model, score, and answer. |
| 33 | `chat_output` | Flowise | Displays the final response. |

Full details are in `docs/flowise_fastapi_workflow_split.md`.

## Human Review Rule

This system is a decision-support tool. It must preserve this rule in the workflow and LISA output:

`Human credit officer review required.`
