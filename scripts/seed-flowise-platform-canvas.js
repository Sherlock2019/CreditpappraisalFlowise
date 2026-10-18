// Add or refresh the "Enterprise Platform" lane on the Docfactor Full Banking Workflow canvas.
// Only nodes whose id starts with "platform_" are replaced; every other node, edge and canvas edit is kept.
//
//   node scripts/seed-flowise-platform-canvas.js
const path = require("path");
const fs = require("fs");
const sqlite3 = require("../.tools/flowise-3.1.2/node_modules/sqlite3");
const { withPlatformLane, STAGES } = require("./lib/platform-canvas");

const WORKFLOW_FLOW_ID = "7a1d2c3e-5b4f-4c6d-8e9f-0a1b2c3d4e5f";
const dbPath = path.join(__dirname, "..", "bank-credit-ai-poc", "flowise", ".flowise", "database.sqlite");

function query(db, sql, params = []) {
  return new Promise((resolve, reject) => db.all(sql, params, (error, rows) => (error ? reject(error) : resolve(rows))));
}

async function main() {
  if (!fs.existsSync(dbPath)) {
    console.log(`Flowise database not found yet: ${dbPath}`);
    return;
  }
  const db = new sqlite3.Database(dbPath);
  try {
    const [flow] = await query(db, "select flowData from chat_flow where id = ?", [WORKFLOW_FLOW_ID]);
    if (!flow) {
      console.log("Full Banking Workflow canvas not seeded yet; seed-flowise-credit-app.js adds the platform lane when it creates it.");
      return;
    }
    const updated = withPlatformLane(JSON.parse(flow.flowData));
    await query(db, "update chat_flow set flowData = ?, updatedDate = ? where id = ?", [JSON.stringify(updated), new Date().toISOString(), WORKFLOW_FLOW_ID]);
    console.log(`Platform lane refreshed on the Full Banking Workflow canvas (${STAGES.length} stages).`);
  } finally {
    await new Promise((resolve) => db.close(resolve));
  }
}

main().catch((error) => {
  console.error(error.message || error);
  process.exit(1);
});
