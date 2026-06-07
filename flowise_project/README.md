# Flowise Project Package

This folder is a Flowise-compatible export/import package generated from the real Docfactor credit appraisal PoC repository.

It maps the existing Streamlit frontend, FastAPI backend, document/RAG workflow, LLM provider switching, and enterprise document connector placeholders into deterministic Flowise-style chatflow JSON.

## Generated Files

- `generated/docfactor-all-in-one-flowise-chatflow.json` - primary one-file import containing the full PoC orchestration.
- `generated/poc-main-chatflow.json` - main frontend/API/RAG/LLM orchestration.
- `generated/poc-rag-document-chatflow.json` - document source, parsing, chunking, embedding, pgvector, and retrieval workflow.
- `generated/poc-api-tools-chatflow.json` - FastAPI endpoint tool workflow.
- `generated/poc-llm-router-chatflow.json` - OpenAI, DeepSeek, and Local Mistral via Ollama provider routing.
- `generated/poc-workspace-export.json` - workspace metadata wrapper.

## Templates

- `templates/app-components-map.json` - scan results from the real repo.
- `templates/flowise-node-map.json` - repo component to Flowise node mapping.
- `templates/credentials-placeholders.json` - provider credential placeholders.
- `templates/environment-placeholders.json` - document source and connector env placeholders.

## Requirements

- Python 3.
- Running Flowise for API import.
- Flowise API key if your instance requires it.
- Running PoC backend for tool execution.
- Provider credentials or local Ollama depending on the selected model path.

## Validate

```bash
python3 flowise_project/validate-flowise-json.py
```

## Import Through UI

1. Start Flowise.
2. Open `Chatflows`.
3. Click `Add New`.
4. Use `Load Chatflow` / `Import`.
5. Select `flowise_project/generated/docfactor-all-in-one-flowise-chatflow.json`.
6. Reconnect credentials.
7. Save and test.

## Import Through API

Copy the example environment:

```bash
cp flowise_project/.env.flowise.example flowise_project/.env.flowise
```

Edit `.env.flowise`, then import:

```bash
bash flowise_project/import-flowise-chatflow.sh --all
```

or:

```bash
python3 flowise_project/import-flowise-chatflow.py --file flowise_project/generated/poc-main-chatflow.json --deploy false
```

For the single all-in-one canvas:

```bash
python3 flowise_project/import-flowise-chatflow.py --file flowise_project/generated/docfactor-all-in-one-flowise-chatflow.json --deploy false
```

## Configure Credentials

Generated JSON does not contain real secrets. Attach credentials in Flowise UI or provide them through secure environment variables.

Provider placeholders:

- `OPENAI_API_KEY`
- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`
- `OLLAMA_BASE_URL`
- `OLLAMA_LOCAL_MODEL`

## Test

Start the PoC services and then follow `docs/FLOWISE_TEST_PLAN.md`.

## Troubleshooting

- If import fails with `401`, set `FLOWISE_API_KEY`.
- If local model calls fail, start Ollama and pull a Mistral model.
- If backend tools fail, confirm `POC_BACKEND_BASE_URL`.
- If credentials are missing, reconnect them manually in Flowise UI.
- If a Flowise node type differs by version, use the generated JSON as a conservative React Flow map and adjust the component in Flowise UI.

## Assumptions

- The generated files are intentionally conservative React Flow-compatible maps.
- Exact Flowise node internals vary by Flowise version, so manual credential and node reconnection may be required after import.
- Enterprise connectors beyond S3 are represented from existing placeholder classes and UI forms, not as completed vendor integrations.
