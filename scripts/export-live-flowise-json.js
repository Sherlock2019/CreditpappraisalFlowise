const fs = require("fs");
const path = require("path");
const sqlite3 = require("../.tools/flowise-3.1.2/node_modules/sqlite3");

const chatflowId = process.argv[2] || "6f946e8b-2d35-4fd4-9ff9-158db1f0b820";
const root = path.join(__dirname, "..");
const dbPath = path.join(root, "bank-credit-ai-poc", "flowise", ".flowise", "database.sqlite");
const outPath = path.join(root, "flowise_project", "generated", "live-flowise-chatflow-from-db.json");
const flowDataPath = path.join(root, "flowise_project", "generated", "live-flowise-flowdata-from-db.json");
const uiImportPath = path.join(root, "flowise_project", "generated", "live-flowise-ui-import-from-db.json");
const apiImportPath = path.join(root, "flowise_project", "generated", "live-flowise-api-import-from-db.json");

const db = new sqlite3.Database(dbPath);

db.get("select * from chat_flow where id = ?", [chatflowId], (error, row) => {
  if (error) {
    console.error(error);
    process.exitCode = 1;
    db.close();
    return;
  }
  if (!row) {
    console.error(`No chat_flow row found for ${chatflowId}`);
    process.exitCode = 1;
    db.close();
    return;
  }

  const flowData = JSON.parse(row.flowData);
  const exportPayload = {
    id: row.id,
    name: row.name,
    description: "Exact export from the live Flowise SQLite chat_flow row.",
    deployed: Boolean(row.deployed),
    isPublic: Boolean(row.isPublic),
    type: row.type,
    category: row.category,
    apiConfig: row.apiConfig ? JSON.parse(row.apiConfig) : undefined,
    analytic: row.analytic ? JSON.parse(row.analytic) : undefined,
    chatbotConfig: row.chatbotConfig ? JSON.parse(row.chatbotConfig) : undefined,
    speechToText: row.speechToText ? JSON.parse(row.speechToText) : undefined,
    followUpPrompts: row.followUpPrompts ? JSON.parse(row.followUpPrompts) : undefined,
    textToSpeech: row.textToSpeech ? JSON.parse(row.textToSpeech) : undefined,
    flowData,
  };
  const apiPayload = {
    ...exportPayload,
    flowData: JSON.stringify(flowData),
  };

  fs.writeFileSync(outPath, `${JSON.stringify(exportPayload, null, 2)}\n`);
  fs.writeFileSync(flowDataPath, `${JSON.stringify(flowData, null, 2)}\n`);
  fs.writeFileSync(uiImportPath, `${JSON.stringify(exportPayload, null, 2)}\n`);
  fs.writeFileSync(apiImportPath, `${JSON.stringify(apiPayload, null, 2)}\n`);
  console.log(JSON.stringify({
    chatflow_id: row.id,
    name: row.name,
    updatedDate: row.updatedDate,
    node_count: Array.isArray(flowData.nodes) ? flowData.nodes.length : 0,
    export_file: outPath,
    flowdata_file: flowDataPath,
    ui_import_file: uiImportPath,
    api_import_file: apiImportPath,
  }, null, 2));
  db.close();
});
