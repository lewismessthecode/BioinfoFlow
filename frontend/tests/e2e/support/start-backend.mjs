import { spawn } from "node:child_process"
import fs from "node:fs"
import path from "node:path"

const authMode = process.env.PLAYWRIGHT_AUTH_MODE || "dev"
const frontendRoot = process.cwd()
const repoRoot = path.resolve(frontendRoot, "..")
const backendRoot = path.resolve(repoRoot, "backend")
const backendPort = Number(process.env.PLAYWRIGHT_BACKEND_PORT || 8100)
const stateRoot = path.resolve(frontendRoot, ".playwright-e2e", "run-lifecycle")
const bioinfoflowHome = path.join(stateRoot, "bioinfoflow-home")
const databasePath = path.join(stateRoot, "bioinfoflow.db")

const env = {
  ...process.env,
  AUTH_MODE: authMode,
  BIOINFOFLOW_HOME: bioinfoflowHome,
  DATABASE_URL: `sqlite+aiosqlite:///${databasePath}`,
  SCHEDULER_POLL_INTERVAL: "30",
  PYTEST_CURRENT_TEST: process.env.PYTEST_CURRENT_TEST || "playwright-e2e",
  BIOINFOFLOW_E2E_FAKE_DOCKER: "1",
}

fs.rmSync(stateRoot, { recursive: true, force: true })
fs.mkdirSync(stateRoot, { recursive: true })

function runStep(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd: backendRoot,
      env,
      stdio: "inherit",
    })

    child.on("exit", (code, signal) => {
      if (signal) {
        reject(new Error(`${command} ${args.join(" ")} exited with signal ${signal}`))
        return
      }
      if (code !== 0) {
        reject(new Error(`${command} ${args.join(" ")} exited with code ${code}`))
        return
      }
      resolve()
    })

    child.on("error", reject)
  })
}

async function main() {
  await runStep("uv", ["run", "python", "-m", "alembic", "upgrade", "head"])

  const server = spawn(
    "uv",
    [
      "run",
      "python",
      "-m",
      "uvicorn",
      "app.main:app",
      "--host",
      "127.0.0.1",
      "--port",
      String(backendPort),
    ],
    {
      cwd: backendRoot,
      env,
      stdio: "inherit",
    },
  )

  const forwardSignal = (signal) => {
    if (!server.killed) {
      server.kill(signal)
    }
  }

  process.on("SIGINT", forwardSignal)
  process.on("SIGTERM", forwardSignal)

  server.on("exit", (code, signal) => {
    process.off("SIGINT", forwardSignal)
    process.off("SIGTERM", forwardSignal)

    if (signal) {
      process.kill(process.pid, signal)
      return
    }
    process.exit(code ?? 0)
  })

  server.on("error", (error) => {
    throw error
  })
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
