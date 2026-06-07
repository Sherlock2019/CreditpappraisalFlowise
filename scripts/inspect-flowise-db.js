const path = require("path");
const sqlite3 = require("../.tools/flowise-3.1.2/node_modules/sqlite3");

const dbPath = path.join(__dirname, "..", "bank-credit-ai-poc", "flowise", ".flowise", "database.sqlite");
const db = new sqlite3.Database(dbPath);

db.all("select name, sql from sqlite_master where type = 'table' order by name", (error, rows) => {
  if (error) {
    console.error(error);
    process.exitCode = 1;
    db.close();
    return;
  }

  for (const row of rows) {
    console.log(`--- ${row.name} ---`);
    console.log(row.sql);
  }
  db.close();
});
