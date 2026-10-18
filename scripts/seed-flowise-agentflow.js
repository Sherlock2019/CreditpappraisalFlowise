// Seed the credit appraisal Agentflow (local dev profile) into the local Flowise database.
// Like ensure-flowise-flows.js, an existing flow is never overwritten, so canvas edits are kept.
//
//   node scripts/seed-flowise-agentflow.js
//
// Environment:
//   BACKEND_PORT / FASTAPI_BASE_URL   where the agentflow calls FastAPI (default http://127.0.0.1:8000)
//   LOCAL_LLM_MODEL                   Ollama chat model with tool calling (default: first installed one)
//   OLLAMA_BASE_URL_FOR_FLOWISE       Ollama URL seen by Flowise (default http://127.0.0.1:11434)
//   FLOWISE_RESEED=1                  rebuild the agentflow even when it exists
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const sqlite3 = require("../.tools/flowise-3.1.2/node_modules/sqlite3");

// Agentflow called by FastAPI when start.sh runs with FLOWISE_FLOW=agentflow.
const AGENTFLOW_ID = "b3c1d7e2-4a5f-4e8b-9c6d-2f1a0e9d8c7b";
const AGENTFLOW_NAME = "Docfactor Credit Appraisal Agent · Local Dev";
// Case data FastAPI may override per request (overrideConfig.vars).
const OVERRIDABLE_VARS = [
  "customer_id", "session_id", "loan_amount", "collateral_value",
  "monthly_income", "monthly_debt_payments", "term_months", "officer_id",
];

const root = path.join(__dirname, "..");
const dbPath = path.join(root, "bank-credit-ai-poc", "flowise", ".flowise", "database.sqlite");
const generator = path.join(root, "flowise_project", "agentflows", "build-agentflows.js");
const generatedFlow = path.join(root, "flowise_project", "agentflows", "generated", "docfactor-credit-appraisal-agentflow-local-dev.json");
const ollamaBaseUrl = (process.env.OLLAMA_BASE_URL_FOR_FLOWISE || "http://127.0.0.1:11434").replace(/\/$/, "");
const fastapiBaseUrl = (process.env.FASTAPI_BASE_URL || `http://127.0.0.1:${process.env.BACKEND_PORT || 8000}`).replace(/\/$/, "");

function query(db, sql, params = []) {
  return new Promise((resolve, reject) => {
    db.all(sql, params, (error, rows) => (error ? reject(error) : resolve(rows)));
  });
}

// Structured outputs need tool calling, so prefer an installed Ollama model that advertises it.
async function toolCallingModel() {
  if (process.env.LOCAL_LLM_MODEL) return process.env.LOCAL_LLM_MODEL;
  try {
    const response = await fetch(`${ollamaBaseUrl}/api/tags`, { signal: AbortSignal.timeout(5000) });
    const models = (await response.json()).models || [];
    const withTools = models.find((model) => (model.capabilities || []).includes("tools"));
    if (withTools) return withTools.name;
    console.log("No installed Ollama model advertises tool calling. Run: ollama pull llama3.1");
  } catch (error) {
    console.log(`Could not list Ollama models at ${ollamaBaseUrl}: ${error.message}`);
  }
  return "llama3.1:latest";
}

async function upsertVariable(db, workspaceId, name, value, overwrite) {
  const [existing] = await query(db, "select id from variable where name = ? and workspaceId = ?", [name, workspaceId]);
  const now = new Date().toISOString();
  if (!existing) {
    await query(
      db,
      "insert into variable (id, name, value, type, createdDate, updatedDate, workspaceId) values (?, ?, ?, 'static', ?, ?, ?)",
      [crypto.randomUUID(), name, value, now, now, workspaceId]
    );
  } else if (overwrite) {
    await query(db, "update variable set value = ?, updatedDate = ? where id = ?", [value, now, existing.id]);
  }
}

async function main() {
  if (!fs.existsSync(dbPath)) {
    console.log(`Flowise database not found yet: ${dbPath}. Start Flowise once, then run this again.`);
    process.exit(2);
  }

  const db = new sqlite3.Database(dbPath);
  try {
    const [workspace] = await query(db, "select id from workspace order by createdDate limit 1");
    if (!workspace) {
      console.log("Flowise has no workspace yet. Open the Flowise UI, create the account, then run this again.");
      process.exit(2);
    }

    // The FastAPI URL follows the port start.sh picked, so refresh it on every launch.
    await upsertVariable(db, workspace.id, "fastapi_base_url", fastapiBaseUrl, true);
    await upsertVariable(db, workspace.id, "officer_id", "credit-officer", false);

    const [existing] = await query(db, "select id from chat_flow where id = ?", [AGENTFLOW_ID]);
    if (existing && process.env.FLOWISE_RESEED !== "1") {
      console.log(`Agentflow already present: ${AGENTFLOW_ID} (fastapi_base_url=${fastapiBaseUrl})`);
      return;
    }

    const model = await toolCallingModel();
    const result = spawnSync(process.execPath, [generator], {
      stdio: "inherit",
      env: { ...process.env, LOCAL_LLM_MODEL: model, LOCAL_LLM_BASE_URL: `${ollamaBaseUrl}/v1` },
    });
    if (result.status !== 0) throw new Error(`build-agentflows.js failed with exit code ${result.status}`);

    const flowData = fs.readFileSync(generatedFlow, "utf8");
    const apiConfig = JSON.stringify({
      overrideConfig: {
        status: true,
        nodes: {},
        variables: OVERRIDABLE_VARS.map((name) => ({ id: name, name, type: "static", enabled: true })),
      },
    });
    const now = new Date().toISOString();
    await query(
      db,
      `insert into chat_flow
        (id, name, flowData, deployed, isPublic, apiConfig, category, type, workspaceId, createdDate, updatedDate)
       values (?, ?, ?, 1, 0, ?, 'Banking Credit Appraisal', 'AGENTFLOW', ?, ?, ?)
       on conflict(id) do update set
        name = excluded.name,
        flowData = excluded.flowData,
        apiConfig = excluded.apiConfig,
        type = excluded.type,
        workspaceId = excluded.workspaceId,
        updatedDate = excluded.updatedDate`,
      [AGENTFLOW_ID, AGENTFLOW_NAME, flowData, apiConfig, workspace.id, now, now]
    );
    console.log(`Seeded agentflow ${AGENTFLOW_ID} using Ollama model ${model}; FastAPI at ${fastapiBaseUrl}.`);
  } finally {
    await new Promise((resolve) => db.close(resolve));
  }
}

main().catch((error) => {
  console.error(error.message || error);
  process.exit(1);
});
