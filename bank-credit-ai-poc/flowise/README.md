# Flowise Design For This POC

For the fastest reliable POC, let FastAPI own retrieval and use Flowise mainly as the orchestration layer.

## Recommended Chatflow

```text
Chat Input
   |
   v
Prompt Template
   |
   v
HTTP Tool / Backend Retrieval API
   |
   v
LLM Node: OpenAI or DeepSeek
   |
   v
Output Parser
   |
   v
Chat Output
```

Flowise should:

- Accept the user question
- Accept retrieved context from the backend
- Apply the banking safety prompt
- Call OpenAI or DeepSeek
- Return a structured answer

## Why FastAPI Owns Retrieval

- FastAPI has `customer_id`
- FastAPI can enforce permissions later
- FastAPI queries PostgreSQL with pgvector
- Flowise handles prompt and model orchestration
- This split is easier to debug

## Backend RAG Flow

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

## Backend Integration

Set these variables in `.env`:

```env
FLOWISE_API_URL=http://flowise:3000
FLOWISE_CHATFLOW_ID=your-flowise-chatflow-id
```

The backend posts to:

```text
{FLOWISE_API_URL}/api/v1/prediction/{FLOWISE_CHATFLOW_ID}
```

If Flowise fails, the backend logs `flowise_error` and falls back to direct LLM calling.

For `custom_public_api`, FastAPI skips Flowise and calls the provider directly. User-submitted custom API keys are not sent to Flowise; Flowise receives only provider/model metadata for non-custom providers.

## Banking Safety Prompt

Use this inside both backend and Flowise:

```text
You are a banking credit analysis assistant.

You provide decision support only. You must not approve or reject loans.

Use only the provided context from customer documents and bank policies.
If evidence is missing, say what is missing.
Always include citations using document name and page number when available.
Always include: "Human credit officer review required."

Return the answer using this structure:

1. Short Answer
2. Risk Level: Low / Medium / High / Insufficient Evidence
3. Preliminary Heuristic Score if available
4. Key Evidence
5. Strengths
6. Weaknesses / Risks
7. Missing Documents or Data
8. Suggested Follow-up Questions
9. Citations
10. Human Review Required

Do not invent facts.
Do not expose unnecessary sensitive personal data.
Do not make a final credit decision.
```

## Example Chatbot Questions

- Summarize this customer's credit risk.
- What are the main financial weaknesses in the uploaded documents?
- Is there evidence of overdue debt or default?
- What documents are missing for a complete credit review?
- Compare this customer against the bank credit policy.
- Give me a preliminary risk level with citations.
- Which financial indicators should a human credit officer review?

## Run Commands

```bash
cd bank-credit-ai-poc
cp .env.example .env
nano .env
docker compose up --build
```

Open:

```text
Backend Swagger: http://localhost:8000/docs
Streamlit UI:    http://localhost:8501
Flowise UI:      http://localhost:3000
Postgres:        localhost:5432
```
