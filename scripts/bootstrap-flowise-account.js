// Create the local Flowise admin account on first run, so launching never stops at the Flowise sign-up page.
//
// Flowise 3.1.2 has no setting to turn its login off. This removes the manual step instead: on a fresh
// Flowise database it registers a local dev account and saves the login to a 0600 file next to the
// database (git-ignored). If an account already exists it changes nothing.
//
//   node scripts/bootstrap-flowise-account.js
//
// Environment (all optional):
//   FLOWISE_PORT            default 3001
//   FLOWISE_LOGIN_EMAIL     default admin@credit-ai.local
//   FLOWISE_LOGIN_NAME      default admin
//   FLOWISE_LOGIN_PASSWORD  default: generated
//   FLOWISE_DATABASE_DIR    default bank-credit-ai-poc/flowise/.flowise
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const sqlite3 = require("../.tools/flowise-3.1.2/node_modules/sqlite3");

const root = path.join(__dirname, "..");
const dataDir = process.env.FLOWISE_DATABASE_DIR || path.join(root, "bank-credit-ai-poc", "flowise", ".flowise");
const dbPath = path.join(dataDir, "database.sqlite");
const loginPath = path.join(dataDir, "launcher-login");
const flowiseUrl = `http://127.0.0.1:${process.env.FLOWISE_PORT || 3001}`;

function query(db, sql, params = []) {
  return new Promise((resolve, reject) => db.all(sql, params, (error, rows) => (error ? reject(error) : resolve(rows))));
}

// Flowise requires upper, lower, digit and special characters, 8+ long.
function generatePassword() {
  return `Ca1!${crypto.randomBytes(12).toString("base64url")}`;
}

async function userCount() {
  if (!fs.existsSync(dbPath)) return 0;
  const db = new sqlite3.Database(dbPath);
  try {
    const [row] = await query(db, "select count(*) as n from user");
    return row.n;
  } catch (error) {
    // Flowise creates its tables on first start; no table yet means no account yet.
    return 0;
  } finally {
    await new Promise((resolve) => db.close(resolve));
  }
}

async function main() {
  if ((await userCount()) > 0) {
    if (fs.existsSync(loginPath)) {
      const { email } = JSON.parse(fs.readFileSync(loginPath, "utf8"));
      console.log(`Flowise login: ${email} (password in ${loginPath})`);
    } else {
      console.log("Flowise account already exists; nothing to create. Forgot the password? FLOWISE_LOGIN_EMAIL=... FLOWISE_LOGIN_NAME=... FLOWISE_LOGIN_PASSWORD=... node scripts/reset-flowise-user-password.js");
    }
    return;
  }

  const login = {
    name: process.env.FLOWISE_LOGIN_NAME || "admin",
    email: process.env.FLOWISE_LOGIN_EMAIL || "admin@credit-ai.local",
    password: process.env.FLOWISE_LOGIN_PASSWORD || generatePassword(),
  };
  const response = await fetch(`${flowiseUrl}/api/v1/account/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user: { name: login.name, email: login.email, credential: login.password } }),
    signal: AbortSignal.timeout(30000),
  });
  if (!response.ok) {
    throw new Error(`Flowise account registration failed (${response.status}): ${(await response.text()).slice(0, 300)}`);
  }
  fs.mkdirSync(dataDir, { recursive: true });
  fs.writeFileSync(loginPath, JSON.stringify({ email: login.email, password: login.password }, null, 2) + "\n", { mode: 0o600 });
  console.log(`Created the local Flowise account ${login.email}; login saved to ${loginPath}`);
}

main().catch((error) => {
  console.error(error.message || error);
  process.exit(1);
});
