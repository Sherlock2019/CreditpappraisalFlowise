# Docfactor credit appraisal Agentflows (OpenStack production + AWS staging)

Flowise 3.1 **Agentflow v2** definitions for the runtime part of the hybrid architecture. They run as governed runs: FastAPI starts each run, gives every agent its own run-bound identity, owns the human approval gate and records the decision. See [`docs/FLOWISE_INTEGRATION.md`](../../docs/FLOWISE_INTEGRATION.md) for the security model.

| File | Environment | Nodes |
| --- | --- | --- |
| `generated/docfactor-credit-appraisal-agentflow-openstack-production.json` | OpenStack Kubernetes, private Llama on vLLM | 48 |
| `generated/docfactor-credit-appraisal-agentflow-aws-staging.json` | AWS EKS replica, candidate Llama on vLLM, evaluation judge | 51 |
| `generated/docfactor-credit-appraisal-agentflow-local-dev.json` | Laptop: same graph as production, local Ollama (`/v1`) | 48 |

`*-api-import.json` files wrap the same flow for `POST /api/v1/chatflows`.

## Launch locally

```bash
AUTH_DEV_MODE=true AUTH_DEV_JWT_SECRET=$(openssl rand -hex 32) ./start.sh
```

- `scripts/ensure-flowise-flows.js` runs `scripts/seed-flowise-agentflow.js`. That seeds the local-dev Agentflow (id `b3c1d7e2-4a5f-4e8b-9c6d-2f1a0e9d8c7b`), sets `fastapi_base_url`, and sets the variable allow-list: the run context plus one `agent_token_<agent>` per agent identity. The model is the first installed Ollama model with tool calling, or whatever `LOCAL_LLM_MODEL` names. A non-thinking model such as `llama3.1` or `qwen2.5` is recommended; see the live verification notes.
- An Agentflow seeded before the tool gateway is upgraded automatically, and the old graph is saved to `bank-credit-ai-poc/flowise/backups/`. To rebuild anyway: `FLOWISE_RESEED=1 node scripts/seed-flowise-agentflow.js`.
- FastAPI calls this flow only from `POST /api/v1/agents/execute` (`FLOWISE_AGENTFLOW_ID`). `/chat` keeps using the RAG chatflow (`FLOWISE_CHATFLOW_ID`). `FLOWISE_FLOW=agentflow` is no longer needed.
- Running the flow from the Flowise canvas stops at Case Intake by design: it has no run id and no agent tokens.

## One flow per environment

Deploy one Flowise per environment, each holding only its own Agentflow. OpenStack runs the production flow, AWS runs the staging flow, and your laptop runs local-dev. The graph is the same in all three; only the model endpoint, the credential and the audit source change, and AWS adds the evaluation judge. These live in the model config, which Flowise doesn't template, so each environment needs its own generated file.

## Flow

```
Loan Officer Request ─ Case Intake (requires run_id from FastAPI) ─ Main Credit Appraisal Agent · Router
   ├─ Q&A ── evidence.search [loan_officer_qa] ─ Q&A Agent ─ audit ─ reply
   └─ Appraisal
        evidence.search ×4, one identity each: credit_scoring / asset_appraisal / legal_policy / fraud_aml
        ─ Evidence Pack ─ Credit Scoring ─ Asset Appraisal ─ Legal ─ Fraud agents
        ─ policy.score [main] (deterministic DTI · LTV · rate)
        ─ Completeness Gate ─┬─ incomplete → audit → "request more information"
                             └─ ready → Recommendation Memo
                                 [AWS only: Evaluation Judge → audit as evaluation_judge]
                                 ─ approval.request [main] ─ Human Approval (pause)
                                     FastAPI: POST /api/v1/approvals/{id}/decision by a second officer → resume
                                     ├─ proceed → approval.read → decision recorded? ─ yes → email.draft → audit → reply
                                     │                                                └ no  → audit → "No decision recorded"
                                     └─ reject  → approval.read → decision recorded? ─ yes → audit → reply
                                                                                      └ no  → audit → "No decision recorded"
```

Design rules built into the generator:
- **The LLM never decides.** DTI, LTV, rate and reason codes come from the FastAPI rules engine. Only an authenticated officer records a decision, at FastAPI. The flow only reads it back, and the customer email is drafted from the recorded decision.
- **One identity per HTTP node.** Each node sends `Authorization: Bearer {{ $vars.agent_token_<agent> }}`. The generator refuses to build a node whose agent lacks the tool's scope in `bank-credit-ai-poc/backend/app/auth/agent_permissions.json`.
- **Typed bodies.** Request bodies are built in Custom Function nodes with `JSON.stringify` and match the Pydantic tool schemas, which reject unknown fields. Enum values produced by the LLM are coerced before they are sent.
- **Audit everywhere.** Every branch ends with an audit event. Actor, tenant, run and correlation id are set by FastAPI from the token.

## Setup in Flowise (non-local environments)

1. **Import:** Agentflows → Add New → ⚙ → Load Agentflow → pick the JSON. Save it with the name from the matching `-api-import.json`.
2. **Variables:** create `fastapi_base_url` (Static). Do not create the run variables; FastAPI sends them.
3. **Override allow-list:** Agentflow → Configuration → Security → Override Configuration. Enable *Variables* for `run_id`, `tenant_id`, `correlation_id`, `requested_by`, `customer_id`, `session_id`, the loan fields, and every `agent_token_<agent>`. Leave `fastapi_base_url` off the list so callers cannot redirect tool calls.
4. **Model:** every LLM node uses *ChatOpenAI Custom* pointed at vLLM:
   - prod: `http://vllm-llama.credit-ai.svc.cluster.local:8000/v1`, model `credit-llama-prod`
   - staging: `http://vllm-llama.credit-ai-staging.svc.cluster.local:8000/v1`, model `credit-llama-candidate`

   Override these at generation time with `OPENSTACK_VLLM_BASE_URL`, `OPENSTACK_VLLM_MODEL`, `AWS_VLLM_BASE_URL` and `AWS_VLLM_MODEL`. Structured output requires vLLM to run with `--enable-auto-tool-choice --tool-call-parser llama3_json`. ChatOpenAI Custom needs an API key: run vLLM with `--api-key <token>`, create a Flowise *OpenAI API* credential holding it, and pass its id when generating (`OPENSTACK_VLLM_CREDENTIAL_ID` / `AWS_VLLM_CREDENTIAL_ID`).
5. **Private hosts:** by default Flowise blocks HTTP calls to private ranges, which includes Kubernetes service IPs. Set `HTTP_SECURITY_CHECK=false` and `HTTP_DENY_LIST=0.0.0.0,169.254.0.0/16,fd00:ec2::254`, which keeps cloud metadata blocked. Then restrict Flowise egress to FastAPI and vLLM with a NetworkPolicy. `start-flowise.sh` sets the same values locally.
6. **Flowise API key:** bind the flow to a Flowise API key and set the same key as FastAPI's `FLOWISE_API_KEY`, so only FastAPI can start or resume runs.

## Regenerate and validate

```bash
node flowise_project/agentflows/build-agentflows.js
node flowise_project/agentflows/validate-agentflows.js
.venv/bin/python scripts/export_tool_schemas.py   # after changing a tool's Pydantic model
```

The generator reads node definitions from `.tools/flowise-3.1.2/node_modules/flowise-components`; set `FLOWISE_COMPONENTS_DIR` to use another install. The validator checks:
- **Wiring and references:** graph wiring and upstream references.
- **Security rules:** registered tools only, one agent identity per node with the right scope, tokens never in prompts, code or replies, no decision fields, correlation header present.
- **Dry runs:** 9 paths with mocked FastAPI and LLM responses, checking every HTTP body against `tool-schemas.json`. The paths include Proceed or Reject clicked in Flowise with no authenticated decision, an LLM inventing a recommendation value, and a direct Flowise call without a governed run.

`pytest` runs the validator too (`tests/test_agentflows.py`).
