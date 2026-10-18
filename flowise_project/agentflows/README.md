# Docfactor credit appraisal Agentflows (OpenStack production + AWS staging)

Two Flowise 3.1 **Agentflow v2** definitions that implement the runtime part of the hybrid architecture (CI/CD is intentionally out of scope).

| File | Environment | Nodes |
| --- | --- | --- |
| `generated/docfactor-credit-appraisal-agentflow-openstack-production.json` | OpenStack Kubernetes, private Llama on vLLM | 43 |
| `generated/docfactor-credit-appraisal-agentflow-aws-staging.json` | AWS EKS replica, candidate Llama on vLLM, evaluation judge | 46 |
| `generated/docfactor-credit-appraisal-agentflow-local-dev.json` | Laptop: same graph as production, local Ollama (`/v1`) | 43 |

`*-api-import.json` files wrap the same flow for `POST /api/v1/chatflows`.

## Launch locally

```bash
FLOWISE_FLOW=agentflow ./start.sh
```

- `scripts/ensure-flowise-flows.js` runs `scripts/seed-flowise-agentflow.js`. That seeds the local-dev agentflow (id `b3c1d7e2-4a5f-4e8b-9c6d-2f1a0e9d8c7b`), turns on variable overrides, and sets `fastapi_base_url`. The model is the first installed Ollama model with tool calling, or whatever `LOCAL_LLM_MODEL` names.
- `start.sh` points FastAPI's `FLOWISE_CHATFLOW_ID` at the agentflow. Without `FLOWISE_FLOW=agentflow` the old RAG chatflow is used as before.
- If FastAPI is already running, stop it first. It reads `FLOWISE_CHATFLOW_ID` only at startup.
- After regenerating, reseed with `FLOWISE_RESEED=1 node scripts/seed-flowise-agentflow.js`.

## One flow per environment

Deploy one Flowise per environment, each holding only its own agentflow. OpenStack runs the production flow. AWS runs the staging flow. Your laptop runs local-dev. The graph is the same in all three; only the model endpoint, the credential and the audit source change, and AWS adds the evaluation judge. These live in the model config, which Flowise doesn't template, so each environment needs its own generated file. No environment needs a chatflow.

## Flow

```
Loan Officer Request ─ Case Intake ─ Main Credit Appraisal Agent · Router
   ├─ Q&A ── retrieval (pgvector) ─ Q&A Agent ─ audit ─ reply
   └─ Appraisal
        retrieval ×4 (credit / asset / legal / fraud evidence)
        ─ Evidence Pack ─ Credit Scoring ─ Asset Appraisal ─ Legal ─ Fraud agents
        ─ Credit Rules & Risk Controls (/loan-policy/score, deterministic)
        ─ Completeness Gate ─┬─ incomplete → audit → "request more information"
                             └─ ready → Recommendation Memo
                                 [AWS only: Evaluation Judge → evaluation event]
                                 ─ Approval Committee ─ Human Approval · Credit Officer
                                     ├─ proceed → /final-decision (Temenos write-back) → email DRAFT → audit → reply
                                     └─ reject  → deferred to manual underwriting → audit → reply
```

Design rules baked in:
- The LLM never decides. DTI, LTV, rate and reason codes come from the FastAPI rules engine. A credit officer approves every decision. Customer emails are drafts only.
- Each specialist returns structured JSON with `chunk_id` citations. Request bodies are built in Custom Function nodes with `JSON.stringify`, so quotes and newlines in LLM text can't break the JSON.
- Every branch ends with an `/audit` event.

## Is a separate Chatflow needed?

No. The Router sends free-form questions to the Q&A branch, so this Agentflow replaces the classic RAG chatflow. The only reason to keep the old chatflow is if `/chat` should stay unchanged during migration, since it still sends `pgMetadataFilter` to a chatflow vector-store node.

## Setup in Flowise

1. **Import:** Agentflows → Add New → ⚙ → Load Agentflow → pick the JSON. Save it with the name from the matching `-api-import.json`.
2. **Variables** (Flowise → Variables, type *Static*): `fastapi_base_url`, `customer_id`, `session_id`, `loan_amount`, `collateral_value`, `monthly_income`, `monthly_debt_payments`, `term_months`, `officer_id`. Staging also needs `expected_decision`. Default values are only used for canvas testing.
3. **Allow FastAPI to override them:** Agentflow → Configuration → Security → Override Configuration. Enable it and allow *Variables*. FastAPI already sends `overrideConfig.vars` (`backend/app/flowise/client.py`).
4. **Model:** every LLM node uses *ChatOpenAI Custom* pointed at vLLM:
   - prod: `http://vllm-llama.credit-ai.svc.cluster.local:8000/v1`, model `credit-llama-prod`
   - staging: `http://vllm-llama.credit-ai-staging.svc.cluster.local:8000/v1`, model `credit-llama-candidate`

   Override these at generation time with `OPENSTACK_VLLM_BASE_URL`, `OPENSTACK_VLLM_MODEL`, `AWS_VLLM_BASE_URL` and `AWS_VLLM_MODEL`. Structured output requires vLLM to run with `--enable-auto-tool-choice --tool-call-parser llama3_json`.
   **Required:** ChatOpenAI Custom refuses to start without an API key. Run vLLM with `--api-key <token>`, create a Flowise *OpenAI API* credential holding that token, and either select it on each LLM node or pass its id when generating (`OPENSTACK_VLLM_CREDENTIAL_ID` / `AWS_VLLM_CREDENTIAL_ID`).
5. **Service auth:** attach an *HTTP Bearer Token* credential to the HTTP nodes once FastAPI enforces auth. `backend/app/security.py` is still a POC placeholder.
6. **Required: private hosts.** By default Flowise blocks HTTP calls to 10/8, 172.16/12, 192.168/16 and 127/8, which includes Kubernetes service IPs. Set `HTTP_SECURITY_CHECK=false` and `HTTP_DENY_LIST=0.0.0.0,169.254.0.0/16,fd00:ec2::254`, which keeps cloud metadata blocked. Then restrict Flowise egress to FastAPI and vLLM with a NetworkPolicy. `start-flowise.sh` sets the same values locally.

## Calling it from FastAPI

- Set `FLOWISE_CHATFLOW_ID` to the Agentflow id. The existing `{question, overrideConfig: {vars}}` payload works as is.
- When the flow reaches *Human Approval*, Flowise returns the memo plus an `action` with the human-input node id. Resume with the same `chatId`:

```json
{ "question": "", "chatId": "<same chat id>",
  "humanInput": { "type": "proceed", "startNodeId": "humanInputAgentflow_0", "feedback": "optional officer note" } }
```

  Use `"type": "reject"` to defer the case. The backend client doesn't handle this resume step yet.

## Regenerate and validate

```bash
node flowise_project/agentflows/build-agentflows.js
node flowise_project/agentflows/validate-agentflows.js
```

The generator reads node definitions from `.tools/flowise-3.1.2/node_modules/flowise-components`; set `FLOWISE_COMPONENTS_DIR` to use another install. The validator checks graph wiring and upstream references, then dry-runs all five paths with mocked FastAPI and LLM responses. On each path it executes the Custom Function code and checks that every HTTP body is valid JSON with the fields FastAPI requires.
