const fs = require("fs");
const path = require("path");
const sqlite3 = require("../.tools/flowise-3.1.2/node_modules/sqlite3");

const FLOW_ID = "6f946e8b-2d35-4fd4-9ff9-158db1f0b820";
const root = path.join(__dirname, "..");
const dbPath = path.join(root, "bank-credit-ai-poc", "flowise", ".flowise", "database.sqlite");
const chatflowPath = path.join(root, "flowise_project", "generated", "live-flowise-chatflow-from-db.json");
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

let chatflow = {};
if (fs.existsSync(chatflowPath)) {
  chatflow = JSON.parse(fs.readFileSync(chatflowPath, "utf8"));
}

const flowName = chatflow.name || "Docfactor Full Banking Workflow";
const deployed = chatflow.deployed === undefined ? true : Boolean(chatflow.deployed);
const isPublic = chatflow.isPublic === undefined ? true : Boolean(chatflow.isPublic);
const apiConfig = JSON.stringify(chatflow.apiConfig || { overrideConfig: true });
const chatbotConfig = JSON.stringify(chatflow.chatbotConfig || {
  starterPrompts: [
    "Summarize this customer's credit risk.",
    "What documents are missing for a complete credit review?",
    "Give me a preliminary risk level with citations.",
  ],
});
const category = chatflow.category || "Banking Credit Appraisal";
const type = chatflow.type || "CHATFLOW";

const backupPath = `${dbPath}.backup-${Date.now()}`;
fs.copyFileSync(dbPath, backupPath);

const db = new sqlite3.Database(dbPath);
db.serialize(() => {
  db.get("select id from workspace order by createdDate asc limit 1", (workspaceError, workspace) => {
    if (workspaceError) {
      console.error(workspaceError);
      process.exitCode = 1;
      db.close();
      return;
    }

    const workspaceId = workspace?.id || null;
    db.get("select id, name from chat_flow where id = ?", [FLOW_ID], (selectError, row) => {
      if (selectError) {
        console.error(selectError);
        process.exitCode = 1;
        db.close();
        return;
      }
      const now = timestamp();
      const sql = row
        ? "update chat_flow set name = ?, flowData = ?, deployed = ?, isPublic = ?, chatbotConfig = ?, apiConfig = ?, category = ?, type = ?, workspaceId = ?, updatedDate = ? where id = ?"
        : "insert into chat_flow (name, flowData, deployed, isPublic, chatbotConfig, apiConfig, category, type, workspaceId, createdDate, updatedDate, id) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)";
      const params = row
        ? [flowName, JSON.stringify(flowData), deployed, isPublic, chatbotConfig, apiConfig, category, type, workspaceId, now, FLOW_ID]
        : [flowName, JSON.stringify(flowData), deployed, isPublic, chatbotConfig, apiConfig, category, type, workspaceId, now, now, FLOW_ID];

      db.run(
        sql,
        params,
        function updateFlow(updateError) {
          if (updateError) {
            console.error(updateError);
            process.exitCode = 1;
          } else {
            console.log(JSON.stringify({
              flow_id: FLOW_ID,
              name: flowName,
              operation: row ? "updated" : "inserted",
              changed_rows: this.changes,
              nodes: flowData.nodes.length,
              edges: flowData.edges.length,
              workspace_id: workspaceId,
              backup: backupPath,
            }, null, 2));
          }
          db.close();
        }
      );
    });
  });
});
