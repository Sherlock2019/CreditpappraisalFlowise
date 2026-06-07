# Flowise Node Mapping

## Frontend Input

Real source:

- `bank-credit-ai-poc/frontend/streamlit_app.py`
- `index.html`

Flowise mapping:

- `node_start`
- `node_frontend_entry`

The Streamlit UI collects customer profile data, document source settings, uploaded files, LLM provider selection, chat prompts, and credit assessment requests.

## Backend API Tool

Real source:

- `bank-credit-ai-poc/backend/app/routers/*.py`

Flowise mapping:

- `node_api_call_tool`
- `node_backend_tool_router`
- `node_api_backend`

The generated API tool workflow maps the real FastAPI endpoints for health, customers, documents, ingestion, retrieval, chat, credit assessment, and connectors.

## RAG Retriever

Real source:

- `bank-credit-ai-poc/backend/app/rag.py`
- `bank-credit-ai-poc/backend/app/document_parser.py`
- `bank-credit-ai-poc/backend/app/embeddings.py`
- `bank-credit-ai-poc/db/init.sql`

Flowise mapping:

- `node_document_retriever`
- `node_rag_router`
- `node_vector_store`
- `node_embedding`

The PoC stores document chunks in PostgreSQL with pgvector and exposes retrieval through `GET /retrieval/{customer_id}`.

## LLM Router

Real source:

- `bank-credit-ai-poc/backend/app/llm_providers/factory.py`
- `bank-credit-ai-poc/frontend/streamlit_app.py`

Flowise mapping:

- `node_llm_router`

Supported provider paths:

- OpenAI
- DeepSeek via OpenAI-compatible API
- Custom Public API through backend
- Local Mistral via Ollama

## Local Mistral / Ollama Node

Real source:

- `bank-credit-ai-poc/backend/app/llm_providers/ollama_provider.py`

Flowise mapping:

- `node_ollama_mistral`

Only Mistral-family Ollama models are represented for local model mode.

## OpenAI Node

Real source:

- `bank-credit-ai-poc/backend/app/llm_providers/openai_provider.py`

Flowise mapping:

- `node_openai`

Credentials are placeholders and must be reattached in Flowise.

## DeepSeek-Compatible Node

Real source:

- `bank-credit-ai-poc/backend/app/llm_providers/deepseek_provider.py`

Flowise mapping:

- `node_deepseek`

DeepSeek is represented as an OpenAI-compatible chat model with custom base URL.

## Final Answer Node

Real source:

- `bank-credit-ai-poc/backend/app/routers/chat.py`
- `bank-credit-ai-poc/backend/app/routers/credit_assessment.py`

Flowise mapping:

- `node_final_response`

The output must include decision-support guardrails, citations, provider metadata, and human review warning.

## Document Source Connectors

Real source:

- `bank-credit-ai-poc/backend/app/connectors/factory.py`
- `bank-credit-ai-poc/backend/app/connectors/*.py`

Flowise mapping:

- `node_external_connectors`
- `node_backend_tool_router`

Mapped sources:

- Manual Upload
- S3
- SharePoint
- OpenText
- Hyland
- FileNet
- ServiceNow
- Salesforce
- Cloud Storage
