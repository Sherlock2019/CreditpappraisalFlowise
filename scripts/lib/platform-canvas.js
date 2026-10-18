// "Enterprise Platform" lane for the Docfactor Full Banking Workflow canvas.
//
// One Custom Function stage per platform capability, labelled with its real status. Each stage
// returns where the capability is implemented and how it is verified, so the canvas doubles as a
// live map of the codebase. Planned stages name the milestone in docs/IMPLEMENTATION_PLAN.md.
// tests/test_platform_canvas.py checks that every implemented path exists.

const STATUS = { implemented: "Implemented", partial: "Partial", planned: "Planned" };
const ID_PREFIX = "platform_";

const GROUPS = {
  security: "INTEGRATIONS & SECURITY",
  fullstack: "FULL-STACK ENGINEERING",
  ai: "AI & DATA",
  reliability: "CLOUD & RELIABILITY",
};

// Order follows a governed request: identity → API → agents/tools → data → decision → audit → operations.
const STAGES = [
  {
    key: "oidc_sso", group: "security", status: "partial",
    label: "OAuth 2.0 / OIDC SSO Login",
    does: "Validates OIDC bearer tokens (JWKS RS256/ES256, issuer, audience, expiry, tenant claim, Keycloak realm roles). Dev HS256 issuer for laptops.",
    implemented_in: ["bank-credit-ai-poc/backend/app/auth/tokens.py", "bank-credit-ai-poc/backend/app/auth/dependencies.py"],
    verified_by: ["tests/test_agent_gateway.py::test_v1_requires_a_valid_token"],
    next: "Keycloak realm export and PKCE browser login with the React console (IMPLEMENTATION_PLAN M3).",
  },
  {
    key: "scim", group: "security", status: "planned",
    label: "SCIM 2.0 User & Group Provisioning",
    does: "Provision officers and map groups to roles, separate from OIDC login.",
    implemented_in: [], verified_by: [],
    next: "SCIM /Users and /Groups adapter (IMPLEMENTATION_PLAN M5b).",
  },
  {
    key: "tenant_rbac", group: "security", status: "implemented",
    label: "Multi-tenant RBAC (default deny)",
    does: "8 roles mapped to explicit permissions; every /api/v1 route declares one. Customers, runs, approvals and audit are filtered by the caller's tenant; other tenants get 404.",
    implemented_in: ["bank-credit-ai-poc/backend/app/auth/policy.py", "bank-credit-ai-poc/backend/app/services/agent_runtime.py"],
    verified_by: ["tests/test_agent_gateway.py::test_other_tenant_cannot_see_or_act_on_demo_data", "tests/test_agent_gateway.py::test_human_role_cannot_grant_itself_agent_identity_or_platform_data_access"],
    next: "PostgreSQL row-level security as defence in depth.",
  },
  {
    key: "credentials", group: "security", status: "implemented",
    label: "Secure Credential Handling",
    does: "Run-bound, 15-minute agent tokens per agent identity, only in Authorization headers; secrets from env only; audit redaction; .env git-ignored.",
    implemented_in: ["bank-credit-ai-poc/backend/app/auth/tokens.py", "bank-credit-ai-poc/backend/app/audit.py"],
    verified_by: ["tests/test_agent_gateway.py::test_tools_are_disabled_while_the_run_waits_for_a_human", "flowise_project/agentflows/validate-agentflows.js"],
    next: "Vault / external-secrets in Kubernetes (IMPLEMENTATION_PLAN M10).",
  },
  {
    key: "typed_api", group: "fullstack", status: "implemented",
    label: "Typed API v1 (Python · FastAPI · Pydantic)",
    does: "Strict Pydantic contracts (extra=forbid, Literal enums, bounds), one error envelope with correlation id, idempotency keys, OpenAPI at /docs.",
    implemented_in: ["bank-credit-ai-poc/backend/app/schemas_v1.py", "bank-credit-ai-poc/backend/app/errors.py", "bank-credit-ai-poc/backend/app/routers/v1"],
    verified_by: ["tests/test_agent_gateway.py", "tests/test_tool_schemas.py"],
    next: "Customer, document and appraisal v1 endpoints (IMPLEMENTATION_PLAN M1).",
  },
  {
    key: "postgres_model", group: "fullstack", status: "partial",
    label: "PostgreSQL + pgvector Data Model",
    does: "Agent runs, approvals, hash-chained audit, tenant-scoped customers, JSONB and pgvector chunks; tenant-filtered vector search.",
    implemented_in: ["bank-credit-ai-poc/backend/app/models.py", "bank-credit-ai-poc/backend/app/rag.py", "bank-credit-ai-poc/db/init.sql"],
    verified_by: ["tests/test_agent_gateway.py"],
    next: "Alembic migrations and PostgreSQL integration tests (IMPLEMENTATION_PLAN M1).",
  },
  {
    key: "async_distributed", group: "fullstack", status: "partial",
    label: "Distributed & Async Execution",
    does: "FastAPI ↔ Flowise callback protocol: run, pause at human input, resume with fresh credentials; retries with exponential backoff; idempotent run start.",
    implemented_in: ["bank-credit-ai-poc/backend/app/services/agent_runtime.py"],
    verified_by: ["tests/test_agent_gateway.py::test_full_run_pauses_for_human_and_records_decision_by_second_officer", "tests/test_agent_gateway.py::test_idempotency_key_replays_and_rejects_reuse"],
    next: "Asynchronous run start with a durable engine (see Temporal stage).",
  },
  {
    key: "react_console", group: "fullstack", status: "planned",
    label: "React / TypeScript Console",
    does: "Customers & documents, appraisals, agent runs, citations, approval queue, audit history, ops dashboard; typed OpenAPI client.",
    implemented_in: [], verified_by: [],
    next: "web/ Vite + React + TypeScript app (IMPLEMENTATION_PLAN M2). LISA (creditappflowise/) stays as is.",
  },
  {
    key: "agents_tools", group: "ai", status: "implemented",
    label: "LLM Agents & Tool Calling (Agentflow V2)",
    does: "Router + credit, asset, legal, fraud specialists + memo agent with structured outputs; each tool call under its own agent identity and scope.",
    implemented_in: ["flowise_project/agentflows/build-agentflows.js", "bank-credit-ai-poc/backend/app/auth/agent_permissions.json"],
    verified_by: ["flowise_project/agentflows/validate-agentflows.js", "tests/test_agentflows.py"],
    next: "Live structured-output run with a non-thinking local model or vLLM (docs/FLOWISE_INTEGRATION.md).",
  },
  {
    key: "mcp_gateway", group: "ai", status: "partial",
    label: "MCP-style Tool Gateway",
    does: "Typed tools at /api/v1/tools/* with JSON schemas and a scope-filtered manifest; customer and tenant come from the token, never the prompt.",
    implemented_in: ["bank-credit-ai-poc/backend/app/routers/v1/tools.py", "flowise_project/agentflows/tool-schemas.json"],
    verified_by: ["tests/test_agent_gateway.py::test_injected_customer_id_cannot_redirect_tools", "tests/test_agent_gateway.py::test_agent_cannot_use_another_agents_evidence_domain"],
    next: "MCP transport server exposing the same tools (IMPLEMENTATION_PLAN M5).",
  },
  {
    key: "ai_evaluation", group: "ai", status: "partial",
    label: "AI Evaluation & Safety",
    does: "Staging Evaluation Judge (groundedness, citation coverage, policy consistency); adversarial dry runs (invented recommendation, approval without a human, direct Flowise call).",
    implemented_in: ["flowise_project/agentflows/build-agentflows.js", "flowise_project/agentflows/validate-agentflows.js"],
    verified_by: ["tests/test_agentflows.py"],
    next: "Versioned synthetic eval set, recall@k, hallucination rate, CI regression gate (IMPLEMENTATION_PLAN M9).",
  },
  {
    key: "connectors", group: "security", status: "partial",
    label: "Enterprise APIs & SaaS Connectors",
    does: "Connector interface; S3 implemented; SharePoint, Salesforce, ServiceNow, OpenText, Hyland, FileNet are placeholders. Temenos is not implemented.",
    implemented_in: ["bank-credit-ai-poc/backend/app/connectors"],
    verified_by: [],
    next: "Connector v2 with pagination, rate limits, health, Temenos mock (IMPLEMENTATION_PLAN M7).",
  },
  {
    key: "documents", group: "ai", status: "partial",
    label: "Document & Spreadsheet Processing",
    does: "PDF, DOCX, XLSX, CSV and image text extraction with page-aware sections over the synthetic dataset.",
    implemented_in: ["bank-credit-ai-poc/backend/app/document_parser.py", "docfactor_banking_demo_dataset"],
    verified_by: [],
    next: "Parser fixtures for every dataset file type (IMPLEMENTATION_PLAN M7).",
  },
  {
    key: "data_pipeline", group: "ai", status: "partial",
    label: "Data Pipeline: Parse → Chunk → Embed → pgvector",
    does: "Upload, parse, chunk, embed and index into PostgreSQL/pgvector; Flowise vector upsert with tenant-tagged chunks.",
    implemented_in: ["bank-credit-ai-poc/backend/app/routers/documents.py", "bank-credit-ai-poc/backend/app/embeddings.py", "scripts/ensure-flowise-flows.js"],
    verified_by: ["tests/test_document_cache.py"],
    next: "Run ingestion as a durable workflow; one embedding model of record (IMPLEMENTATION_PLAN M6/M7).",
  },
  {
    key: "knowledge_graph", group: "ai", status: "planned",
    label: "Knowledge Graph & Ontology",
    does: "Customer, guarantor, collateral and facility entities and relationships extracted from documents.",
    implemented_in: [], verified_by: [],
    next: "Relational entity/relationship tables first, graph store only if needed (IMPLEMENTATION_PLAN M7).",
  },
  {
    key: "human_approval", group: "security", status: "implemented",
    label: "Human Approval Gate (four-eyes)",
    does: "Only an authenticated officer with approval:decide records the decision, never the one who started the run; approvals expire; Flowise resumes only after FastAPI records it.",
    implemented_in: ["bank-credit-ai-poc/backend/app/routers/v1/approvals.py"],
    verified_by: ["tests/test_agent_gateway.py::test_agent_token_cannot_record_a_credit_decision_anywhere", "tests/test_agent_gateway.py::test_expired_approval_cannot_be_decided"],
    next: "Escalation on expiry via the durable workflow engine.",
  },
  {
    key: "temporal", group: "reliability", status: "planned",
    label: "Durable Workflows (Temporal)",
    does: "Persistent state, retries, timeouts, approval waits with escalation, recovery after restarts for ingestion, appraisal and exports.",
    implemented_in: [], verified_by: [],
    next: "Temporal worker and workflows (IMPLEMENTATION_PLAN M6).",
  },
  {
    key: "audit_chain", group: "security", status: "implemented",
    label: "Tamper-evident Audit",
    does: "Hash-chained audit events per tenant, written in the business transaction; every tool call, denial and decision recorded; chain verification endpoint.",
    implemented_in: ["bank-credit-ai-poc/backend/app/services/audit_chain.py", "bank-credit-ai-poc/backend/app/routers/v1/audit.py"],
    verified_by: ["tests/test_agent_gateway.py::test_editing_an_audit_row_breaks_the_chain"],
    next: "Anchor the head hash externally; DB role without UPDATE/DELETE on audit_events.",
  },
  {
    key: "observability", group: "reliability", status: "partial",
    label: "Observability & Troubleshooting",
    does: "Correlation id on every request, Flowise call, tool call and audit event; error envelope; queryable audit API.",
    implemented_in: ["bank-credit-ai-poc/backend/app/correlation.py", "bank-credit-ai-poc/backend/app/errors.py"],
    verified_by: ["tests/test_agent_gateway.py::test_v1_requires_a_valid_token"],
    next: "OpenTelemetry, Prometheus metrics, Grafana dashboards, JSON logs (IMPLEMENTATION_PLAN M8).",
  },
  {
    key: "automated_testing", group: "reliability", status: "implemented",
    label: "Automated Testing",
    does: "pytest suite for the API, security and audit; Agentflow validator with schema checks, security rules and 9 dry-run scenarios per environment.",
    implemented_in: ["tests", "flowise_project/agentflows/validate-agentflows.js"],
    verified_by: ["tests/test_agentflows.py", "tests/test_platform_canvas.py"],
    next: "PostgreSQL integration tests and Playwright E2E with the React console.",
  },
  {
    key: "cicd", group: "reliability", status: "planned",
    label: "CI/CD Pipeline",
    does: "Lint, types, tests, validator, migrations, secret and image scanning, build and deploy.",
    implemented_in: [], verified_by: [],
    next: "GitHub Actions and/or GitLab CI (IMPLEMENTATION_PLAN M10, open decision 4).",
  },
  {
    key: "docker_cloud", group: "reliability", status: "partial",
    label: "Docker · GCP-compatible Deployment",
    does: "Backend and Streamlit images, docker-compose with pgvector and Flowise. No GCP or Kubernetes deployment yet.",
    implemented_in: ["bank-credit-ai-poc/docker-compose.yml", "bank-credit-ai-poc/backend/Dockerfile"],
    verified_by: [],
    next: "Non-root images, Helm chart, staging (GKE or OpenStack) (IMPLEMENTATION_PLAN M10).",
  },
];

const ANCHOR_TYPE = "string | number | boolean | json | array";

function stageNode(stage, position) {
  const id = `${ID_PREFIX}${stage.key}`;
  const summary = {
    component: stage.label,
    status: STATUS[stage.status],
    does: stage.does,
    implemented_in: stage.implemented_in,
    verified_by: stage.verified_by,
    next: stage.next,
  };
  return {
    width: 300,
    height: 560,
    id,
    position,
    positionAbsolute: position,
    type: "customNode",
    selected: false,
    dragging: false,
    data: {
      id,
      label: `[${STATUS[stage.status]}] ${stage.label}`,
      version: 3,
      name: "customFunction",
      type: "CustomFunction",
      baseClasses: ["CustomFunction", "Utilities"],
      category: "Utilities",
      description: stage.does,
      inputParams: [
        { label: "Input Variables", name: "functionInputVariables", type: "json", optional: true, acceptVariable: true, list: true, id: `${id}-input-functionInputVariables-json` },
        { label: "Function Name", name: "functionName", type: "string", optional: true, id: `${id}-input-functionName-string` },
        { label: "Javascript Function", name: "javascriptFunction", type: "code", id: `${id}-input-javascriptFunction-code` },
      ],
      inputAnchors: [{ label: "Input", name: "input", type: ANCHOR_TYPE, optional: true, id: `${id}-input-input-${ANCHOR_TYPE.replace(/ /g, "")}` }],
      inputs: {
        functionInputVariables: "{}",
        functionName: id,
        javascriptFunction: `// ${STATUS[stage.status]}: ${stage.label}\nreturn { ...${JSON.stringify(summary, null, 2)}, input: $input };`,
      },
      outputAnchors: [{ id: `${id}-output-output-${ANCHOR_TYPE.replace(/ /g, "")}`, name: "output", label: "Output", type: ANCHOR_TYPE }],
      outputs: { output: "output" },
      selected: false,
    },
  };
}

function stickyNote(id, note, position) {
  return {
    id,
    position,
    positionAbsolute: position,
    type: "stickyNote",
    width: 300,
    height: 300,
    selected: false,
    dragging: false,
    data: {
      id,
      label: "Sticky Note",
      version: 2,
      name: "stickyNote",
      type: "StickyNote",
      baseClasses: ["StickyNote"],
      category: "Utilities",
      description: "Add a sticky note",
      inputParams: [{ label: "", name: "note", type: "string", rows: 1, optional: true, id: `${id}-input-note-string` }],
      inputAnchors: [],
      inputs: { note },
      outputAnchors: [{ id: `${id}-output-stickyNote-StickyNote`, name: "stickyNote", label: "StickyNote", description: "Add a sticky note", type: "StickyNote" }],
      outputs: {},
      selected: false,
    },
  };
}

function edge(source, target) {
  const sourceHandle = source.data.outputAnchors[0].id;
  const targetHandle = target.data.inputAnchors[0].id;
  return { source: source.id, sourceHandle, target: target.id, targetHandle, type: "buttonedge", id: `${source.id}-${sourceHandle}-${target.id}-${targetHandle}` };
}

function legend() {
  const counts = Object.fromEntries(Object.keys(STATUS).map((s) => [s, STAGES.filter((x) => x.status === s).length]));
  const byGroup = Object.entries(GROUPS)
    .map(([key, title]) => `${title}\n` + STAGES.filter((s) => s.group === key).map((s) => `  [${STATUS[s.status]}] ${s.label}`).join("\n"))
    .join("\n\n");
  return (
    `ENTERPRISE PLATFORM LANE\n\nOne stage per platform capability, in the order a governed request meets them. ` +
    `Labels are the real status: ${counts.implemented} Implemented (code + passing tests), ${counts.partial} Partial, ${counts.planned} Planned.\n` +
    `Run a stage to see where it is implemented, how it is verified and what is next.\n` +
    `The runnable governed path is the Agentflow "Docfactor Credit Appraisal Agent", started by POST /api/v1/agents/execute.\n\n${byGroup}`
  );
}

// Returns a copy of flowData with the platform lane (re)built below the existing canvas.
// Earlier platform nodes are replaced; every other node and edge is kept as is.
function withPlatformLane(flowData) {
  const keep = (flowData.nodes || []).filter((n) => !n.id.startsWith(ID_PREFIX));
  const keepEdges = (flowData.edges || []).filter((e) => !e.source.startsWith(ID_PREFIX) && !e.target.startsWith(ID_PREFIX));
  const left = keep.length ? Math.min(...keep.map((n) => n.position.x)) : 0;
  const bottom = keep.length ? Math.max(...keep.map((n) => n.position.y + (n.height || 600))) : 0;
  const top = bottom + 700;
  const perRow = 11;

  const legendNode = stickyNote(`${ID_PREFIX}legend`, legend(), { x: left - 420, y: top });
  const nodes = STAGES.map((stage, index) =>
    stageNode(stage, { x: left + (index % perRow) * 380, y: top + Math.floor(index / perRow) * 760 })
  );
  const edges = nodes.slice(1).map((node, index) => edge(nodes[index], node));
  // Show where the lane starts in the request: from the chat input stage, when present.
  const chatInput = keep.find((n) => n.id === "chat_input");
  if (chatInput) edges.unshift(edge(chatInput, nodes[0]));

  return { ...flowData, nodes: [...keep, legendNode, ...nodes], edges: [...keepEdges, ...edges] };
}

module.exports = { STAGES, STATUS, ID_PREFIX, withPlatformLane };
