import { spawnSync } from "node:child_process"
import { createRequire } from "node:module"

const require = createRequire(import.meta.url)

function loadBetterSqlite() {
  try {
    require("better-sqlite3")
    return null
  } catch (error) {
    return error
  }
}

const initialError = loadBetterSqlite()

if (!initialError) {
  process.exit(0)
}

const message = String(initialError.message ?? "")
const isAbiMismatch =
  message.includes("compiled against a different Node.js version") ||
  message.includes("NODE_MODULE_VERSION")

if (!isAbiMismatch) {
  console.error(initialError)
  process.exit(1)
}

console.warn("[better-sqlite3] ABI mismatch detected. Rebuilding for current Node.js...")

const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm"
const rebuild = spawnSync(npmCommand, ["rebuild", "better-sqlite3"], {
  stdio: "inherit",
})

if (rebuild.status !== 0) {
  process.exit(rebuild.status ?? 1)
}

const verifyError = loadBetterSqlite()

if (verifyError) {
  console.error(verifyError)
  process.exit(1)
}

console.log("[better-sqlite3] Rebuild successful.")
