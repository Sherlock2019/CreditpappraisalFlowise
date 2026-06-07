# Flowise Test Plan

1. Validate generated JSON.

```bash
python3 flowise_project/validate-flowise-json.py
```

2. Import into Flowise UI.

- Import `poc-main-chatflow.json`.
- Confirm all nodes appear.
- Confirm credentials are placeholders.

3. Import via API.

```bash
bash flowise_project/import-flowise-chatflow.sh --all
```

4. Test OpenAI path.

- Attach OpenAI credential.
- Set model to one of the listed OpenAI models.
- Ask a credit-risk question.

5. Test DeepSeek path.

- Attach DeepSeek credential.
- Confirm custom base URL points to DeepSeek.
- Ask a credit-risk question.

6. Test Local Mistral via Ollama path.

- Start Ollama.
- Pull a Mistral model.
- Confirm `OLLAMA_BASE_URL` and model match.
- Ask a credit-risk question.

7. Test backend API tool call.

- Confirm `POC_BACKEND_BASE_URL`.
- Call health, customer, document, and retrieval endpoints.

8. Test document upload/RAG query.

- Upload a document through Streamlit.
- Ingest it.
- Run a retrieval query.
- Confirm citations are returned.

9. Test missing credentials behavior.

- Import without provider credentials.
- Confirm the error is clear and no secret is printed.

10. Test no secrets in JSON.

- Run validator.
- Manually inspect generated files for real keys.
