// Make sure the local Flowise database holds the credit appraisal flows.
// Existing flows are never overwritten, so edits made in the Flowise canvas are kept.
//
//   node scripts/ensure-flowise-flows.js
//
// Environment:
//   FLOWISE_OLLAMA_BASE_URL  Ollama URL used by the backend flow (default http://127.0.0.1:11434)
//   FLOWISE_OLLAMA_MODEL     Ollama model used by the backend flow (default: first installed chat model)
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const sqlite3 = require("../.tools/flowise-3.1.2/node_modules/sqlite3");

// Runnable flow called by FastAPI through /api/v1/prediction/<id>.
const BACKEND_FLOW_ID = "6f946e8b-2d35-4fd4-9ff9-158db1f0b820";
// Full 16-stage workflow canvas, kept for reference and design.
const WORKFLOW_FLOW_ID = "7a1d2c3e-5b4f-4c6d-8e9f-0a1b2c3d4e5f";

const root = path.join(__dirname, "..");
const dbPath = path.join(root, "bank-credit-ai-poc", "flowise", ".flowise", "database.sqlite");
const workflowPath = path.join(root, "flowise_project", "generated", "live-flowise-flowdata-from-db.json");
const ollamaBaseUrl = (process.env.FLOWISE_OLLAMA_BASE_URL || "http://127.0.0.1:11434").replace(/\/$/, "");

function query(db, sql, params = []) {
  return new Promise((resolve, reject) => {
    db.all(sql, params, (error, rows) => (error ? reject(error) : resolve(rows)));
  });
}

function run(script, args, env) {
  const result = spawnSync(process.execPath, [path.join(__dirname, script), ...args], {
    stdio: "inherit",
    env: { ...process.env, ...env },
  });
  if (result.status !== 0) throw new Error(`${script} failed with exit code ${result.status}`);
}

async function pickOllamaModel() {
  if (process.env.FLOWISE_OLLAMA_MODEL) return process.env.FLOWISE_OLLAMA_MODEL;
  const wanted = process.env.OLLAMA_MODEL || "mistral:7b-instruct";
  try {
    const response = await fetch(`${ollamaBaseUrl}/api/tags`, { signal: AbortSignal.timeout(5000) });
    const names = ((await response.json()).models || []).map((model) => model.name);
    const chatModels = names.filter((name) => !/embed/i.test(name));
    if (names.includes(wanted)) return wanted;
    const sameFamily = chatModels.find((name) => name.split(":")[0] === wanted.split(":")[0]);
    if (sameFamily) return sameFamily;
    if (chatModels.length) {
      console.log(`Ollama model ${wanted} is not installed; the backend flow will use ${chatModels[0]}.`);
      return chatModels[0];
    }
  } catch (error) {
    console.log(`Could not list Ollama models at ${ollamaBaseUrl}: ${error.message}`);
  }
  return wanted;
}

async function main() {
  if (!fs.existsSync(dbPath)) {
    console.log(`Flowise database not found yet: ${dbPath}. Start Flowise once, then run this again.`);
    process.exit(2);
  }

  const db = new sqlite3.Database(dbPath);
  const workspaces = await query(db, "select id from workspace limit 1");
  const flows = await query(db, "select id from chat_flow where id in (?, ?)", [BACKEND_FLOW_ID, WORKFLOW_FLOW_ID]);
  await new Promise((resolve) => db.close(resolve));

  if (!workspaces.length) {
    console.log("Flowise has no workspace yet. Open the Flowise UI, create the account, then run this again.");
    process.exit(2);
  }

  const existing = new Set(flows.map((flow) => flow.id));

  if (existing.has(BACKEND_FLOW_ID)) {
    console.log(`Backend flow already present: ${BACKEND_FLOW_ID}`);
  } else {
    run("seed-flowise-credit-app.js", [], {
      SEED_UPDATE_ENV: "0",
      FLOWISE_OLLAMA_BASE_URL: ollamaBaseUrl,
      FLOWISE_OLLAMA_MODEL: await pickOllamaModel(),
    });
  }

  if (existing.has(WORKFLOW_FLOW_ID)) {
    console.log(`Workflow canvas already present: ${WORKFLOW_FLOW_ID}`);
  } else if (fs.existsSync(workflowPath)) {
    run("import-flowise-json-to-db.js", [workflowPath, WORKFLOW_FLOW_ID], {});
  }
}

main().catch((error) => {
  console.error(error.message || error);
  process.exit(1);
});
