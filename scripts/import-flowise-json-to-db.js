const fs = require("fs");
const path = require("path");
const sqlite3 = require("../.tools/flowise-3.1.2/node_modules/sqlite3");

const DEFAULT_FLOW_ID = "6f946e8b-2d35-4fd4-9ff9-158db1f0b820";
const root = path.join(__dirname, "..");
const dbPath = path.join(root, "bank-credit-ai-poc", "flowise", ".flowise", "database.sqlite");
const inputPath = process.argv[2]
  ? path.resolve(process.argv[2])
  : path.join(root, "flowise_project", "generated", "live-flowise-flowdata-from-db.json");
const flowId = process.argv[3] || DEFAULT_FLOW_ID;

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

function parseJson(value, label) {
  if (typeof value !== "string") return value;
  try {
    return JSON.parse(value);
  } catch (error) {
    throw new Error(`${label} contains invalid JSON: ${error.message}`);
  }
}

function normalizePayload(payload) {
  const flowData = parseJson(payload.flowData || payload, "flowData");
  if (!Array.isArray(flowData.nodes) || !Array.isArray(flowData.edges)) {
    throw new Error("Import file must contain Flowise nodes and edges");
  }

  return {
    name: payload.name || "Docfactor Full Banking Workflow",
    deployed: payload.deployed === undefined ? true : Boolean(payload.deployed),
    isPublic: payload.isPublic === undefined ? true : Boolean(payload.isPublic),
    type: payload.type || "CHATFLOW",
    category: payload.category || "Banking Credit Appraisal",
    apiConfig: payload.apiConfig || { overrideConfig: true },
    chatbotConfig: payload.chatbotConfig || {
      starterPrompts: [
        "Summarize this customer's credit risk.",
        "What documents are missing for a complete credit review?",
        "Give me a preliminary risk level with citations.",
      ],
    },
    flowData,
  };
}

const payload = normalizePayload(parseJson(fs.readFileSync(inputPath, "utf8"), inputPath));
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
    db.get("select id from chat_flow where id = ?", [flowId], (selectError, row) => {
      if (selectError) {
        console.error(selectError);
        process.exitCode = 1;
        db.close();
        return;
      }

      const now = timestamp();
      const fields = [
        payload.name,
        JSON.stringify(payload.flowData),
        payload.deployed,
        payload.isPublic,
        JSON.stringify(payload.chatbotConfig),
        JSON.stringify(payload.apiConfig),
        payload.category,
        payload.type,
        workspaceId,
      ];
      const sql = row
        ? "update chat_flow set name = ?, flowData = ?, deployed = ?, isPublic = ?, chatbotConfig = ?, apiConfig = ?, category = ?, type = ?, workspaceId = ?, updatedDate = ? where id = ?"
        : "insert into chat_flow (name, flowData, deployed, isPublic, chatbotConfig, apiConfig, category, type, workspaceId, createdDate, updatedDate, id) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)";
      const params = row ? [...fields, now, flowId] : [...fields, now, now, flowId];

      db.run(sql, params, function importFlow(error) {
        if (error) {
          console.error(error);
          process.exitCode = 1;
        } else {
          console.log(JSON.stringify({
            flow_id: flowId,
            name: payload.name,
            operation: row ? "updated" : "inserted",
            changed_rows: this.changes,
            nodes: payload.flowData.nodes.length,
            edges: payload.flowData.edges.length,
            workspace_id: workspaceId,
            backup: backupPath,
          }, null, 2));
        }
        db.close();
      });
    });
  });
});
