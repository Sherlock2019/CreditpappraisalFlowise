// Make sure the local Flowise database holds the credit appraisal flows.
// Existing flows are never overwritten, so edits made in the Flowise canvas are kept.
//
//   node scripts/ensure-flowise-flows.js
//
// Environment:
//   FLOWISE_PORT / FLOWISE_URL  running Flowise, used to load the documents into pgvector
//   FLOWISE_OLLAMA_BASE_URL     Ollama URL used by the backend flow (default http://127.0.0.1:11434)
//   FLOWISE_OLLAMA_MODEL        chat model (default: an installed chat model)
//   FLOWISE_EMBEDDING_MODEL     embedding model (default: an installed embedding model)
//   FLOWISE_RESEED=1            rebuild the backend flow even when it exists
//   FLOWISE_SKIP_UPSERT=1       seed the flow without loading the documents
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");
const sqlite3 = require("../.tools/flowise-3.1.2/node_modules/sqlite3");

// Runnable flow called by FastAPI through /api/v1/prediction/<id>.
const BACKEND_FLOW_ID = "6f946e8b-2d35-4fd4-9ff9-158db1f0b820";
// Placeholder canvas imported by an earlier version of this script.
const MOCKUP_FLOW_ID = "7a1d2c3e-5b4f-4c6d-8e9f-0a1b2c3d4e5f";

const root = path.join(__dirname, "..");
const dbPath = path.join(root, "bank-credit-ai-poc", "flowise", ".flowise", "database.sqlite");
const apiKeyPath = path.join(path.dirname(dbPath), "launcher-api-key");
const RAG_TABLE = process.env.FLOWISE_RAG_PG_TABLE || "flowise_rag_chunks";
const API_KEY_NAME = "credit-appraisal-launcher";
const API_KEY_PERMISSIONS = ["chatflows:view", "chatflows:update", "documentStores:upsert-config"];
const ollamaBaseUrl = (process.env.FLOWISE_OLLAMA_BASE_URL || "http://127.0.0.1:11434").replace(/\/$/, "");
const flowiseUrl = (process.env.FLOWISE_URL || `http://127.0.0.1:${process.env.FLOWISE_PORT || 3001}`).replace(/\/$/, "");

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

async function installedOllamaModels() {
  try {
    const response = await fetch(`${ollamaBaseUrl}/api/tags`, { signal: AbortSignal.timeout(5000) });
    return ((await response.json()).models || []).map((model) => model.name);
  } catch (error) {
    console.log(`Could not list Ollama models at ${ollamaBaseUrl}: ${error.message}`);
    return [];
  }
}

// Use the wanted model when it is installed, otherwise the first installed one of the same kind.
function pickModel(names, wanted, isEmbedding, label) {
  const candidates = names.filter((name) => /embed/i.test(name) === isEmbedding);
  if (names.includes(wanted)) return wanted;
  const sameFamily = candidates.find((name) => name.split(":")[0] === wanted.split(":")[0]);
  if (sameFamily) return sameFamily;
  if (candidates.length) {
    console.log(`Ollama ${label} model ${wanted} is not installed; the backend flow will use ${candidates[0]}.`);
    return candidates[0];
  }
  if (names.length) console.log(`No Ollama ${label} model is installed. Run: ollama pull ${wanted}`);
  return wanted;
}

// The vector upsert API needs a Flowise API key. Create one for this launcher the same way
// Flowise does (random key, scrypt hash as secret) and keep it next to the Flowise database.
async function launcherApiKey() {
  if (process.env.FLOWISE_API_KEY) return process.env.FLOWISE_API_KEY;
  if (fs.existsSync(apiKeyPath)) return fs.readFileSync(apiKeyPath, "utf8").trim();

  const apiKey = crypto.randomBytes(32).toString("base64url");
  const salt = crypto.randomBytes(8).toString("hex");
  const apiSecret = `${crypto.scryptSync(apiKey, salt, 64).toString("hex")}.${salt}`;

  const db = new sqlite3.Database(dbPath);
  const [workspace] = await query(db, "select id from workspace order by createdDate limit 1");
  await query(
    db,
    "insert into apikey (id, apiKey, apiSecret, keyName, workspaceId, permissions) values (?, ?, ?, ?, ?, ?)",
    [crypto.randomUUID(), apiKey, apiSecret, API_KEY_NAME, workspace.id, JSON.stringify(API_KEY_PERMISSIONS)]
  );
  await new Promise((resolve) => db.close(resolve));

  fs.writeFileSync(apiKeyPath, `${apiKey}\n`, { mode: 0o600 });
  console.log(`Created Flowise API key "${API_KEY_NAME}" (stored in ${apiKeyPath}).`);
  return apiKey;
}

function ragDatabase() {
  const { Client } = require("../.tools/flowise-3.1.2/node_modules/pg");
  return new Client({
    host: process.env.FLOWISE_RAG_PG_HOST || "localhost",
    port: Number(process.env.FLOWISE_RAG_PG_PORT || 5432),
    database: process.env.FLOWISE_RAG_PG_DATABASE || "credit_ai",
    user: process.env.POSTGRES_VECTORSTORE_USER || process.env.DB_USER || "credit_ai_user",
    password: process.env.POSTGRES_VECTORSTORE_PASSWORD || process.env.DB_PASSWORD || "credit_ai_password",
  });
}

async function storedChunkCount() {
  const client = ragDatabase();
  try {
    await client.connect();
    const result = await client.query(`select count(*)::int as chunks from ${RAG_TABLE}`);
    return result.rows[0].chunks;
  } catch (error) {
    return 0; // table not created yet
  } finally {
    await client.end().catch(() => {});
  }
}

// Each customer's files live in a CUST-nnn folder; copy that id into the chunk metadata
// so retrieval can be filtered to the selected customer.
async function tagChunksWithCustomer() {
  const client = ragDatabase();
  try {
    await client.connect();
    const result = await client.query(
      `update ${RAG_TABLE}
          set metadata = metadata || jsonb_build_object('customer', substring(metadata->>'source' from 'CUST-[0-9]+'))
        where metadata->>'source' ~ 'CUST-[0-9]+' and not (metadata ? 'customer')`
    );
    console.log(`Tagged ${result.rowCount} chunks with their customer id.`);
  } catch (error) {
    console.log(`Could not tag chunks with customer ids: ${error.message}`);
  } finally {
    await client.end().catch(() => {});
  }
}

// Chunk, embed and store the customer documents in PostgreSQL through the flow's own nodes.
async function upsertDocuments() {
  const chunks = await storedChunkCount();
  if (chunks > 0 && process.env.FLOWISE_FORCE_UPSERT !== "1") {
    console.log(`PostgreSQL vector store already holds ${chunks} chunks; skipping the document load.`);
    return;
  }
  const url = `${flowiseUrl}/api/v1/vector/upsert/${BACKEND_FLOW_ID}`;
  const apiKey = await launcherApiKey();
  console.log(`Loading documents into the PostgreSQL vector store through ${url} (this can take several minutes)...`);
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${apiKey}` },
    body: "{}",
    signal: AbortSignal.timeout(3600 * 1000),
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`Vector upsert failed (${response.status}): ${text.slice(0, 400)}`);
  console.log(`Vector upsert result: ${text.slice(0, 400)}`);
}

async function main() {
  if (!fs.existsSync(dbPath)) {
    console.log(`Flowise database not found yet: ${dbPath}. Start Flowise once, then run this again.`);
    process.exit(2);
  }

  const db = new sqlite3.Database(dbPath);
  const workspaces = await query(db, "select id from workspace limit 1");
  const flows = await query(db, "select id from chat_flow where id in (?, ?)", [BACKEND_FLOW_ID, MOCKUP_FLOW_ID]);
  await new Promise((resolve) => db.close(resolve));

  if (!workspaces.length) {
    console.log("Flowise has no workspace yet. Open the Flowise UI, create the account, then run this again.");
    process.exit(2);
  }

  const existing = new Set(flows.map((flow) => flow.id));

  if (existing.has(BACKEND_FLOW_ID) && process.env.FLOWISE_RESEED !== "1") {
    console.log(`Backend flow already present: ${BACKEND_FLOW_ID}`);
  } else {
    const models = await installedOllamaModels();
    run("seed-flowise-credit-app.js", [], {
      SEED_UPDATE_ENV: "0",
      FLOWISE_OLLAMA_BASE_URL: ollamaBaseUrl,
      FLOWISE_OLLAMA_MODEL: process.env.FLOWISE_OLLAMA_MODEL
        || pickModel(models, process.env.OLLAMA_MODEL || "mistral:7b-instruct", false, "chat"),
      FLOWISE_EMBEDDING_MODEL: process.env.FLOWISE_EMBEDDING_MODEL
        || pickModel(models, "embeddinggemma:latest", true, "embedding"),
    });
    if (process.env.FLOWISE_SKIP_UPSERT !== "1") await upsertDocuments();
    await tagChunksWithCustomer();
  }

  // The 16-box placeholder canvas an earlier version imported is not a working flow; remove it.
  if (existing.has(MOCKUP_FLOW_ID)) {
    const cleanup = new sqlite3.Database(dbPath);
    await query(cleanup, "delete from chat_flow where id = ?", [MOCKUP_FLOW_ID]);
    await new Promise((resolve) => cleanup.close(resolve));
    console.log(`Removed placeholder canvas: ${MOCKUP_FLOW_ID}`);
  }
}

main().catch((error) => {
  console.error(error.message || error);
  process.exit(1);
});
