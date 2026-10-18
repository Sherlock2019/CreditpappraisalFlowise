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

// Agentflow called by FastAPI's POST /api/v1/agents/execute (FLOWISE_AGENTFLOW_ID).
const AGENTFLOW_ID = "b3c1d7e2-4a5f-4e8b-9c6d-2f1a0e9d8c7b";
const AGENTFLOW_NAME = "Docfactor Credit Appraisal Agent · Local Dev";

const root = path.join(__dirname, "..");
const permissions = require(path.join(root, "bank-credit-ai-poc", "backend", "app", "auth", "agent_permissions.json"));
// Run context FastAPI sends per request (overrideConfig.vars). Flowise drops any var not listed here,
// so fastapi_base_url can never be redirected by a caller.
const OVERRIDABLE_VARS = [
  "run_id", "tenant_id", "correlation_id", "requested_by", "customer_id", "session_id",
  "loan_amount", "collateral_value", "monthly_income", "monthly_debt_payments", "term_months",
  ...Object.keys(permissions.agents).map((agent) => `agent_token_${agent}`),
];
// Flows generated before the tool gateway call the unversioned endpoints; they are upgraded on seed.
const GATEWAY_MARKER = "/api/v1/tools/";
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

    const apiConfig = JSON.stringify({
      overrideConfig: {
        status: true,
        nodes: {},
        variables: OVERRIDABLE_VARS.map((name) => ({ id: name, name, type: "static", enabled: true })),
      },
    });
    const [existing] = await query(db, "select id, flowData from chat_flow where id = ?", [AGENTFLOW_ID]);
    const preGateway = existing && !String(existing.flowData || "").includes(GATEWAY_MARKER);
    if (existing && !preGateway && process.env.FLOWISE_RESEED !== "1") {
      // Keep canvas edits, but always refresh the variable allow-list so new agent identities reach the flow.
      await query(db, "update chat_flow set apiConfig = ?, updatedDate = ? where id = ?", [apiConfig, new Date().toISOString(), AGENTFLOW_ID]);
      console.log(`Agentflow already present: ${AGENTFLOW_ID} (fastapi_base_url=${fastapiBaseUrl}); variable allow-list refreshed.`);
      return;
    }
    if (preGateway) {
      const backupDir = path.join(root, "bank-credit-ai-poc", "flowise", "backups");
      fs.mkdirSync(backupDir, { recursive: true });
      const backupFile = path.join(backupDir, `agentflow-${AGENTFLOW_ID}-${Date.now()}.json`);
      fs.writeFileSync(backupFile, existing.flowData);
      console.log(`Upgrading the pre-gateway Agentflow to the tool-gateway version; previous graph saved to ${backupFile}`);
    }

    const model = await toolCallingModel();
    const result = spawnSync(process.execPath, [generator], {
      stdio: "inherit",
      env: { ...process.env, LOCAL_LLM_MODEL: model, LOCAL_LLM_BASE_URL: `${ollamaBaseUrl}/v1` },
    });
    if (result.status !== 0) throw new Error(`build-agentflows.js failed with exit code ${result.status}`);

    const flowData = fs.readFileSync(generatedFlow, "utf8");
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
