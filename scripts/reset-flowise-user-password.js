const path = require("path");
const sqlite3 = require("../.tools/flowise-3.1.2/node_modules/sqlite3");
const bcrypt = require("../.tools/flowise-3.1.2/node_modules/bcryptjs");

const email = process.env.FLOWISE_LOGIN_EMAIL;
const name = process.env.FLOWISE_LOGIN_NAME;
const password = process.env.FLOWISE_LOGIN_PASSWORD;

if (!email || !name || !password) {
  console.error("Set FLOWISE_LOGIN_EMAIL, FLOWISE_LOGIN_NAME, and FLOWISE_LOGIN_PASSWORD.");
  process.exit(1);
}

const dbPath = path.join(__dirname, "..", "bank-credit-ai-poc", "flowise", ".flowise", "database.sqlite");
const hash = bcrypt.hashSync(password, bcrypt.genSaltSync(12));
const db = new sqlite3.Database(dbPath);

db.run(
  "update user set name = ?, email = ?, credential = ?, status = 'active', updatedDate = current_timestamp where email = ? or name = ?",
  [name, email, hash, email, name],
  function updateUser(error) {
    if (error) {
      console.error(error);
      process.exitCode = 1;
      db.close();
      return;
    }
    if (this.changes === 0) {
      console.error("No matching Flowise user found.");
      process.exitCode = 1;
      db.close();
      return;
    }
    console.log(`Updated Flowise login for ${name} (${email}).`);
    db.close();
  }
);
