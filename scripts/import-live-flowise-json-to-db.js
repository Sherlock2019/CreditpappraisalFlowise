const fs = require("fs");
const path = require("path");
const sqlite3 = require("../.tools/flowise-3.1.2/node_modules/sqlite3");

const FLOW_ID = "6f946e8b-2d35-4fd4-9ff9-158db1f0b820";
const root = path.join(__dirname, "..");
const dbPath = path.join(root, "bank-credit-ai-poc", "flowise", ".flowise", "database.sqlite");
const flowDataPath = path.join(root, "flowise_project", "generated", "live-flowise-flowdata-from-db.json");

function timestamp() {
  const now = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  return [
    now.getFullYear(),
    pad(now.getMonth() + 1),
    pad(now.getDate()),
  ].join("-") + " " + [
    pad(now.getHours()),
    pad(now.getMinutes()),
    pad(now.getSeconds()),
  ].join(":");
}

const flowData = JSON.parse(fs.readFileSync(flowDataPath, "utf8"));
if (!Array.isArray(flowData.nodes) || !Array.isArray(flowData.edges)) {
  throw new Error(`${flowDataPath} does not contain a valid Flowise flowData graph`);
}

const backupPath = `${dbPath}.backup-${Date.now()}`;
fs.copyFileSync(dbPath, backupPath);

const db = new sqlite3.Database(dbPath);
db.serialize(() => {
  db.get("select id, name from chat_flow where id = ?", [FLOW_ID], (selectError, row) => {
    if (selectError) {
      console.error(selectError);
      process.exitCode = 1;
      db.close();
      return;
    }
    if (!row) {
      console.error(`No chat_flow row found for ${FLOW_ID}`);
      process.exitCode = 1;
      db.close();
      return;
    }

    db.run(
      "update chat_flow set flowData = ?, updatedDate = ? where id = ?",
      [JSON.stringify(flowData), timestamp(), FLOW_ID],
      function updateFlow(updateError) {
        if (updateError) {
          console.error(updateError);
          process.exitCode = 1;
        } else {
          console.log(JSON.stringify({
            flow_id: FLOW_ID,
            name: row.name,
            updated_rows: this.changes,
            nodes: flowData.nodes.length,
            edges: flowData.edges.length,
            backup: backupPath,
          }, null, 2));
        }
        db.close();
      }
    );
  });
});
