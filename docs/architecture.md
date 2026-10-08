# Credit Appraisal App Architecture

How the pieces started by `./start.sh` fit together.

## Components

```mermaid
flowchart LR
    user([Credit officer<br/>browser])

    subgraph ui [User interfaces]
        launcher["Credit Appraisal UI<br/>web_proxy.py + creditappflowise/<br/>port 8080"]
        streamlit["Streamlit UI<br/>frontend/streamlit_app.py<br/>port 8501"]
    end

    subgraph core [Application backend]
        api["FastAPI backend<br/>backend/app<br/>port 8000"]
        db[("PostgreSQL + pgvector<br/>port 5432")]
        files[["Uploaded documents<br/>data/uploads"]]
    end

    subgraph ai [AI orchestration]
        flowise["Flowise 3.1.2<br/>port 3001"]
        flowdb[("Flowise SQLite<br/>flowise/.flowise")]
        ollama["Ollama<br/>local LLM<br/>port 11434"]
        cloud["OpenAI / DeepSeek /<br/>custom API"]
    end

    user --> launcher
    user --> streamlit
    user -. "edit flows" .-> flowise
    launcher -- "/api/* proxy" --> api
    streamlit -- "REST" --> api
    api -- "customers, chunks,<br/>embeddings, audit" --> db
    api --> files
    api -- "POST /api/v1/prediction/{flow id}" --> flowise
    flowise --> flowdb
    flowise -- "chat completion" --> ollama
    api -. "fallback when Flowise fails,<br/>or direct provider" .-> ollama
    api -. "direct provider" .-> cloud
```

## Chat request

```mermaid
sequenceDiagram
    actor Officer as Credit officer
    participant UI as Credit Appraisal UI
    participant API as FastAPI
    participant PG as PostgreSQL + pgvector
    participant FW as Flowise
    participant LLM as Ollama

    Officer->>UI: Ask a question about a customer
    UI->>API: POST /api/chat
    API->>PG: Embed question, retrieve top chunks
    PG-->>API: Evidence with citations
    API->>FW: POST /api/v1/prediction/{flow id}
    FW->>LLM: Safety prompt + context + question
    LLM-->>FW: Draft answer
    FW-->>API: Answer
    Note over API,FW: If Flowise fails, FastAPI calls the LLM provider directly
    API->>PG: Store session and audit log
    API-->>UI: Answer, citations, flowise_used
    UI-->>Officer: Decision support (human review required)
```

## Who owns what

| Component | Owns |
| --- | --- |
| Credit Appraisal UI | Static UI in `creditappflowise/`, served by `web_proxy.py`, which forwards `/api/*` to FastAPI. |
| Streamlit UI | Alternative operator UI talking straight to FastAPI. |
| FastAPI | Document upload, parsing, chunking, embeddings, retrieval, loan policy score, committee submission, final human decision, customer email draft, audit log. |
| PostgreSQL + pgvector | Customers, documents, chunks, embeddings, sessions, decisions, audit. |
| Flowise | Prompt template, model selection and the LLM call for chat answers. |
| Ollama | Local model used by the Flowise backend flow. |

## Flowise flows

`scripts/ensure-flowise-flows.js` adds these when they are missing (run automatically by `start.sh`):

| Flow | ID | Purpose |
| --- | --- | --- |
| Docfactor Credit Appraisal RAG Backend | `6f946e8b-2d35-4fd4-9ff9-158db1f0b820` | Runnable flow: Ollama chat model + banking prompt + LLM chain. FastAPI calls it. |
| Docfactor Full Banking Workflow | `7a1d2c3e-5b4f-4c6d-8e9f-0a1b2c3d4e5f` | 16-stage reference canvas of the whole workflow. Not executable as a prediction. |

## Ports

`start.sh` moves a service to the next free port when its default is taken, and prints the URLs it ended up with.

| Service | Default port | Override |
| --- | --- | --- |
| Credit Appraisal UI | 8080 | `WEB_PORT` |
| FastAPI | 8000 | `BACKEND_PORT` |
| Streamlit | 8501 | `STREAMLIT_PORT` |
| Flowise | 3001 | `FLOWISE_PORT` |
| PostgreSQL (Docker stack) | 5432 | `POSTGRES_HOST_PORT` |
| Ollama | 11434 | `OLLAMA_HOST` |
