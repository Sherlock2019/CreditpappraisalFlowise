const fs = require("fs");
const sqlite3 = require("../.tools/flowise-3.1.2/node_modules/sqlite3");

const CHATFLOW_ID = "6f946e8b-2d35-4fd4-9ff9-158db1f0b820";
const MODEL_EXPR = "{{$vars.llm_model}}";
const FLOW_FILES = [
  "flowise_project/generated/best-docfactor-all-in-one-flowise-chatflow.json",
  "bank-credit-ai-poc/flowise/flows/docfactor_credit_appraisal_rag_backend.json",
];

function updateFlowData(flowData) {
  const wasString = typeof flowData === "string";
  const fd = wasString ? JSON.parse(flowData) : flowData;
  for (const node of fd.nodes || []) {
    if (node.id === "ollama_gemma" && node.data?.inputs) {
      node.data.label = "Ollama: Selected Local Model";
      node.data.inputs.modelName = MODEL_EXPR;
    }
    if (node.id === "ollama_mistral" && node.data?.inputs) {
      node.data.label = "Ollama: Mistral Option";
      node.data.inputs.javascriptFunction = [
        "return {",
        '  component: "Ollama Mistral provider option",',
        '  modelName: "mistral",',
        "  selectedModel: $vars?.llm_model,",
        "  input: $input",
        "};",
      ].join("\n");
    }
    if (node.id === "llm_router" && node.data?.inputs) {
      node.data.inputs.javascriptFunction = [
        "return {",
        '  component: "LLM Router",',
        "  selectedProvider: $vars?.llm_provider,",
        "  selectedModel: $vars?.llm_model,",
        "  input: $input",
        "};",
      ].join("\n");
    }
  }
  return wasString ? JSON.stringify(fd) : fd;
}

for (const file of FLOW_FILES) {
  const root = JSON.parse(fs.readFileSync(file, "utf8"));
  if (Array.isArray(root.runtimeVariables) && !root.runtimeVariables.includes("llm_model")) {
    const insertAt = Math.max(root.runtimeVariables.indexOf("llm_provider") + 1, 0);
    root.runtimeVariables.splice(insertAt, 0, "llm_model");
  }
  if (root.flowData) {
    root.flowData = updateFlowData(root.flowData);
    fs.writeFileSync(file, `${JSON.stringify(root, null, 2)}\n`);
  } else {
    const flowData = updateFlowData(root);
    fs.writeFileSync(file, `${JSON.stringify(flowData, null, 2)}\n`);
  }
  console.log(`updated ${file}`);
}

const db = new sqlite3.Database("bank-credit-ai-poc/flowise/.flowise/database.sqlite");
db.get("select flowData from chat_flow where id = ?", [CHATFLOW_ID], (error, row) => {
  if (error) throw error;
  if (!row) throw new Error(`Chatflow not found: ${CHATFLOW_ID}`);
  const flowData = updateFlowData(row.flowData);
  db.run(
    "update chat_flow set flowData = ?, updatedDate = datetime('now') where id = ?",
    [flowData, CHATFLOW_ID],
    (updateError) => {
      if (updateError) throw updateError;
      console.log(`updated live Flowise DB modelName=${MODEL_EXPR}`);
      db.close();
    }
  );
});
