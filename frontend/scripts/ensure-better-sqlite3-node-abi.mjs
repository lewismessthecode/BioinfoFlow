import { spawnSync } from "node:child_process"
import { createRequire } from "node:module"
import { ensureBetterSqliteNodeAbi } from "./better-sqlite3-node-abi.mjs"

const require = createRequire(import.meta.url)

const npmCommand = process.platform === "win32" ? "npm.cmd" : "npm"

try {
  const result = await ensureBetterSqliteNodeAbi({
    loadModule: () => require("better-sqlite3"),
    rebuild: () =>
      spawnSync(npmCommand, ["rebuild", "better-sqlite3"], {
        stdio: "inherit",
      }),
  })

  if (result.action === "rebuild-failed") {
    process.exit(result.status ?? 1)
  }
} catch (error) {
  console.error(error)
  process.exit(1)
}
