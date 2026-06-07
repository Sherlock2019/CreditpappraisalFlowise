const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");
const FLOW_ID = "6f946e8b-2d35-4fd4-9ff9-158db1f0b820";
const FLOW_NAME = "Docfactor Full Banking Workflow";
const flowDataPath = path.join(ROOT, "flowise_project", "generated", "live-flowise-flowdata-from-db.json");
const uiImportPath = path.join(ROOT, "flowise_project", "generated", "live-flowise-ui-import-from-db.json");
const apiImportPath = path.join(ROOT, "flowise_project", "generated", "live-flowise-api-import-from-db.json");

const flow = JSON.parse(fs.readFileSync(flowDataPath, "utf8"));
const nodeById = new Map(flow.nodes.map((node) => [node.id, node]));

function cloneFunctionNode(baseId, id, label, position) {
  const base = nodeById.get(baseId);
  if (!base) throw new Error(`Missing base node ${baseId}`);
  const node = JSON.parse(JSON.stringify(base));
  node.id = id;
  node.position = position;
  node.data.id = id;
  node.data.label = label;
  node.data.description = label;

  for (const param of node.data.inputParams || []) {
    param.id = param.id.replaceAll(baseId, id);
  }
  for (const anchor of node.data.inputAnchors || []) {
    anchor.id = anchor.id.replaceAll(baseId, id);
  }
  for (const anchor of node.data.outputAnchors || []) {
    anchor.id = anchor.id.replaceAll(baseId, id);
  }

  flow.nodes.push(node);
  nodeById.set(id, node);
  return node;
}

if (!nodeById.has("document_status")) {
  cloneFunctionNode("parser", "document_status", "Document Status", { x: 720, y: 390 });
}

function setFunction(id, functionName, javascriptFunction) {
  const node = nodeById.get(id);
  if (!node) throw new Error(`Missing node ${id}`);
  node.data.inputs = {
    ...(node.data.inputs || {}),
    functionInputVariables: "{}",
    functionName,
    javascriptFunction,
  };
}

function setStatusNode(id, label, statusKey) {
  setFunction(
    id,
    statusKey,
    `const input = $input || {};
const status = input.ingestion_status || input.status || {};
return {
  component: "${label}",
  role: "visual_status_only",
  backend_owner: "FastAPI",
  status: status.${statusKey} || input.${statusKey} || "pending",
  document_id: input.document_id || null,
  chunks_count: input.chunks_count || 0,
  input
};`
  );
}

setFunction(
  "runtime_vars",
  "runtime_variables",
  `return {
  component: "Runtime Variables",
  question: $input?.question || $input || "",
  customer_id: $vars?.customer_id || $input?.customer_id || "demo_customer",
  session_id: $vars?.session_id || $input?.session_id || "demo_session",
  user_id: $vars?.user_id || $input?.user_id || "demo_user",
  language: $vars?.language || $input?.language || "en",
  llm_provider: $vars?.llm_provider || $input?.llm_provider || "ollama",
  llm_model: $vars?.llm_model || $input?.llm_model || "mistral",
  policy_mode: $vars?.policy_mode || $input?.policy_mode || "standard_credit_policy",
  require_citations: true,
  require_human_review: true,
  input: $input
};`
);

setFunction(
  "document_upload",
  "document_upload",
  `const input = $input || {};
return {
  component: "Document Upload Trigger / Status",
  role: "http_call_or_status",
  backend_owner: "FastAPI",
  method: "POST",
  endpoint: "http://host.docker.internal:8000/documents/upload",
  expected_form_fields: {
    customer_id: input.customer_id || "demo_customer",
    session_id: input.session_id || "demo_session",
    source: "flowise",
    file: "<uploaded file>"
  },
  input
};`
);

setFunction(
  "document_status",
  "document_status",
  `const input = $input || {};
const documentId = input.document_id || input.id || null;
return {
  component: "Document Status",
  role: "http_call_or_status",
  backend_owner: "FastAPI",
  method: "GET",
  endpoint: documentId ? \`http://host.docker.internal:8000/documents/\${documentId}/status\` : null,
  expected_response: {
    ingestion_status: {
      parser: "pending|complete|failed",
      chunker: "pending|complete|failed",
      embeddings: "pending|complete|failed",
      postgresql: "pending|complete|failed",
      pgvector: "pending|complete|failed"
    }
  },
  input
};`
);

setStatusNode("parser", "Parser Status", "parser");
setStatusNode("chunker", "Chunker Status", "chunker");
setStatusNode("embeddings", "Embeddings Status", "embeddings");
setStatusNode("postgresql", "PostgreSQL Storage Status", "postgresql");
setStatusNode("pgvector", "pgvector Index Status", "pgvector");

setFunction(
  "http_retrieval_tool",
  "http_retrieval_tool",
  `const input = $input || {};
return {
  component: "HTTP Retrieval Tool",
  role: "http_call",
  backend_owner: "FastAPI",
  method: "POST",
  endpoint: "http://host.docker.internal:8000/retrieval/query",
  body: {
    customer_id: input.customer_id || "demo_customer",
    session_id: input.session_id || "demo_session",
    question: input.question || "",
    top_k: 8,
    filters: { policy_mode: input.policy_mode || "standard_credit_policy" }
  },
  input
};`
);

setFunction(
  "retriever",
  "retriever",
  `const input = $input || {};
return {
  component: "Retriever Status",
  role: "visual_status_only",
  backend_owner: "FastAPI",
  evidence_count: (input.evidence || input.retrieved_chunks || []).length,
  input
};`
);

setFunction(
  "citation_builder",
  "citation_builder",
  `const input = $input || {};
const evidence = input.evidence || input.retrieved_evidence || [];

const citations = evidence.map((item, idx) => ({
  citation_id: \`C\${idx + 1}\`,
  document_id: item.document_id || null,
  chunk_id: item.chunk_id || null,
  document_name: item.document_name || "Unknown document",
  page: item.page || null,
  score: item.score || null,
  source_type: item.source_type || "unknown",
  text: item.text || ""
}));

const citation_text = citations.map(c => {
  const pageText = c.page ? \`p.\${c.page}\` : "page unknown";
  return \`[\${c.citation_id}] \${c.document_name}, \${pageText}: \${c.text}\`;
}).join("\\n\\n");

return {
  component: "Citation Builder",
  customer_id: input.customer_id,
  question: input.question,
  citations,
  citation_text,
  missing_documents: input.missing_documents || [],
  input
};`
);

setFunction(
  "loan_policy_scoring",
  "loan_policy_scoring",
  `const input = $input || {};
return {
  component: "Loan Policy Scoring",
  role: "http_call",
  backend_owner: "FastAPI",
  method: "POST",
  endpoint: "http://host.docker.internal:8000/loan-policy/score",
  body: {
    customer_id: input.customer_id || "demo_customer",
    session_id: input.session_id || "demo_session",
    policy_mode: input.policy_mode || "standard_credit_policy",
    question: input.question || "",
    evidence: input.citations || []
  },
  input
};`
);

for (const id of ["dti", "ltv", "interest_rate", "monthly_payment", "recommendation"]) {
  setFunction(
    id,
    id,
    `const input = $input || {};
return {
  component: "${nodeById.get(id).data.label}",
  role: "visual_result_only",
  backend_owner: "FastAPI",
  value: input.${id} || input.policy_score?.${id} || input.input?.${id} || null,
  input
};`
  );
}

setFunction(
  "llm_router",
  "llm_router",
  `const input = $input || {};
const provider = (input.llm_provider || $vars?.llm_provider || "ollama").toLowerCase();
const accepted = ["ollama", "openai", "deepseek", "custom"];
return {
  component: "LLM Router",
  selected_provider: accepted.includes(provider) ? provider : "ollama",
  llm_model: input.llm_model || $vars?.llm_model || "mistral",
  route_mode: "single_selectable_provider",
  input
};`
);

setFunction(
  "ollama_mistral",
  "ollama_mistral",
  `const input = $input || {};
return {
  component: "Ollama Provider Option",
  provider: "ollama",
  selected: (input.selected_provider || "ollama") === "ollama",
  accepted_models: ["mistral", "mistral:7b", "mistral-small", "gemma", "gemma2:9b", "llama3"],
  model: input.llm_model || "mistral",
  input
};`
);

const ollamaGemma = nodeById.get("ollama_gemma");
ollamaGemma.data.inputs = {
  ...(ollamaGemma.data.inputs || {}),
  baseUrl: "{{ $vars.ollama_base_url || 'http://host.docker.internal:11434' }}",
  modelName: "{{ $vars.llm_model || 'mistral' }}",
  temperature: "{{ $vars.temperature || 0.2 }}",
};

for (const [id, provider] of [
  ["openai_provider", "openai"],
  ["deepseek_provider", "deepseek"],
  ["custom_provider", "custom"],
]) {
  setFunction(
    id,
    provider,
    `const input = $input || {};
return {
  component: "${nodeById.get(id).data.label} Provider Option",
  provider: "${provider}",
  selected: input.selected_provider === "${provider}",
  model: input.llm_model || "",
  secure_config: "env_vars",
  input
};`
  );
}

const promptNode = nodeById.get("prompt_template");
promptNode.data.inputs = {
  ...(promptNode.data.inputs || {}),
  template: `You are LISA, the Loan Intelligent Scoring Agent inside HyperSpeed Banking Agent.

You are a banking credit analysis assistant.
You provide decision support only.
You must not approve or reject loans.
A human credit officer or approval committee must make the final decision.

Use only:
1. Retrieved customer document evidence
2. Citation context
3. Bank policy/scoring data supplied by FastAPI
4. Runtime workflow state

If evidence is missing, say exactly what is missing.
Always include citations using document name and page number when available.
Always include the sentence: "Human credit officer review required."

Runtime:
Customer ID: {customer_id}
Session ID: {session_id}
Language: {language}
Policy mode: {policy_mode}
LLM provider: {llm_provider}
LLM model: {llm_model}

User question:
{question}

Retrieved citation evidence:
{citation_text}

Missing documents:
{missing_documents}

Policy scoring result:
{policy_score}

Return the answer in this exact structure:

1. Short Answer
2. Risk Level
3. Preliminary Heuristic Score if available
4. Key Evidence
5. Strengths
6. Weaknesses / Risks
7. Missing Documents or Data
8. Loan Policy Scoring
9. Approval Committee / Final Decision Status
10. Suggested Follow-up Questions
11. Citations
12. Human Review Required`,
  promptValues: "{}",
};

setFunction(
  "output_parser",
  "output_parser",
  `const raw = $input?.text || $input?.answer || $input || "";
return {
  short_answer: "",
  risk_level: "",
  heuristic_score: null,
  key_evidence: [],
  strengths: [],
  weaknesses: [],
  missing_documents: [],
  loan_policy_scoring: {},
  approval_committee_status: "",
  final_decision_status: "human_review_required",
  suggested_follow_up_questions: [],
  citations: [],
  human_review_required: true,
  raw_answer: String(raw)
};`
);

setFunction(
  "credit_assessment",
  "credit_assessment",
  `const input = $input || {};
return {
  component: "Credit Assessment Explanation",
  role: "decision_support_only",
  human_review_required: true,
  input
};`
);

for (const [id, functionName, endpoint] of [
  ["approval_committee", "approval_committee", "/approval-committee/submit"],
  ["final_decision", "final_decision", "/final-decision"],
  ["customer_email_draft", "customer_email_draft", "/customer-decision-email/draft"],
]) {
  setFunction(
    id,
    functionName,
    `const input = $input || {};
return {
  component: "${nodeById.get(id).data.label}",
  role: "http_call_or_status",
  backend_owner: "FastAPI",
  method: "POST",
  endpoint: "http://host.docker.internal:8000${endpoint}",
  human_review_required: true,
  input
};`
  );
}

setFunction(
  "audit_logging",
  "audit_logging",
  `const input = $input || {};
return {
  component: "Audit Logging",
  role: "http_call",
  backend_owner: "FastAPI",
  method: "POST",
  endpoint: "http://host.docker.internal:8000/audit",
  body: {
    customer_id: input.customer_id || "demo_customer",
    session_id: input.session_id || "demo_session",
    user_id: input.user_id || "demo_user",
    workflow_id: "${FLOW_ID}",
    workflow_name: "${FLOW_NAME}",
    question: input.question || "",
    llm_provider: input.llm_provider || "ollama",
    llm_model: input.llm_model || "mistral",
    evidence_ids: (input.citations || []).map(c => c.chunk_id).filter(Boolean),
    policy_score: input.policy_score || {},
    final_answer: input.parsed_output || input,
    human_review_required: true
  },
  input
};`
);

setFunction(
  "chat_output",
  "chat_output",
  `const input = $input || {};
return {
  component: "Chat Output",
  answer: input.raw_answer || input.answer || input.text || input,
  human_review_required: true
};`
);

function edge(source, target) {
  const sourceHandle = `${source}-output-output-string|number|boolean|json|array`;
  const targetHandle = `${target}-input-input-string|number|boolean|json|array`;
  return {
    source,
    sourceHandle,
    target,
    targetHandle,
    type: "buttonedge",
    id: `${source}-${sourceHandle}-${target}-${targetHandle}`,
  };
}

const pairs = [
  ["chat_input", "runtime_vars"],
  ["runtime_vars", "document_upload"],
  ["document_upload", "document_status"],
  ["document_status", "parser"],
  ["parser", "chunker"],
  ["chunker", "embeddings"],
  ["embeddings", "postgresql"],
  ["postgresql", "pgvector"],
  ["pgvector", "http_retrieval_tool"],
  ["http_retrieval_tool", "retriever"],
  ["retriever", "citation_builder"],
  ["citation_builder", "loan_policy_scoring"],
  ["loan_policy_scoring", "dti"],
  ["loan_policy_scoring", "ltv"],
  ["loan_policy_scoring", "interest_rate"],
  ["interest_rate", "monthly_payment"],
  ["dti", "recommendation"],
  ["ltv", "recommendation"],
  ["monthly_payment", "recommendation"],
  ["recommendation", "prompt_template"],
  ["citation_builder", "prompt_template"],
  ["runtime_vars", "prompt_template"],
  ["prompt_template", "llm_chain"],
  ["runtime_vars", "llm_router"],
  ["llm_router", "ollama_mistral"],
  ["llm_router", "ollama_gemma"],
  ["llm_router", "openai_provider"],
  ["llm_router", "deepseek_provider"],
  ["llm_router", "custom_provider"],
  ["ollama_mistral", "llm_chain"],
  ["ollama_gemma", "llm_chain"],
  ["openai_provider", "llm_chain"],
  ["deepseek_provider", "llm_chain"],
  ["custom_provider", "llm_chain"],
  ["llm_chain", "output_parser"],
  ["output_parser", "credit_assessment"],
  ["credit_assessment", "approval_committee"],
  ["approval_committee", "final_decision"],
  ["final_decision", "customer_email_draft"],
  ["customer_email_draft", "audit_logging"],
  ["audit_logging", "chat_output"],
];
flow.edges = pairs.map(([source, target]) => edge(source, target));

const uiPayload = {
  id: FLOW_ID,
  name: FLOW_NAME,
  description: "Live Flowise/FastAPI banking workflow split: Flowise orchestrates; FastAPI executes backend work.",
  deployed: true,
  isPublic: true,
  type: "CHATFLOW",
  category: "Banking Credit Appraisal",
  runtimeVariables: [
    "customer_id",
    "session_id",
    "user_id",
    "language",
    "llm_provider",
    "llm_model",
    "policy_mode",
    "question",
  ],
  flowData: flow,
};
const apiPayload = { ...uiPayload, flowData: JSON.stringify(flow) };

fs.writeFileSync(flowDataPath, `${JSON.stringify(flow, null, 2)}\n`);
fs.writeFileSync(uiImportPath, `${JSON.stringify(uiPayload, null, 2)}\n`);
fs.writeFileSync(apiImportPath, `${JSON.stringify(apiPayload, null, 2)}\n`);
console.log(JSON.stringify({ flow_id: FLOW_ID, nodes: flow.nodes.length, edges: flow.edges.length, uiImportPath, apiImportPath }, null, 2));
