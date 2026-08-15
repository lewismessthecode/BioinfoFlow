import { spawn } from "node:child_process"
import fs from "node:fs"
import http from "node:http"
import path from "node:path"

const frontendRoot = process.cwd()
const repoRoot = path.resolve(frontendRoot, "..")
const backendRoot = path.resolve(repoRoot, "backend")
const pythonExecutable = path.join(
  backendRoot,
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
)
const backendPort = Number(process.env.PLAYWRIGHT_BACKEND_PORT || 8100)
const controlPort = Number(
  process.env.PLAYWRIGHT_BACKEND_CONTROL_PORT || backendPort + 1,
)
const stateRoot = path.resolve(frontendRoot, ".playwright-e2e", "run-lifecycle")
const bioinfoflowHome = path.join(stateRoot, "bioinfoflow-home")
const databasePath = path.join(stateRoot, "bioinfoflow.db")

const env = {
  ...process.env,
  PATH: [path.dirname(pythonExecutable), process.env.PATH]
    .filter(Boolean)
    .join(path.delimiter),
  AUTH_MODE: "dev",
  BIOINFOFLOW_HOME: bioinfoflowHome,
  BIOINFOFLOW_PUBLIC_API_BASE_URL: `http://127.0.0.1:${backendPort}/api/v1`,
  DATABASE_URL: `sqlite+aiosqlite:///${databasePath}`,
  AGENT_RUN_LEASE_SECONDS: "1",
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

  let backend = spawnBackend()
  let restarting = false
  let shuttingDown = false

  const control = http.createServer(async (request, response) => {
    if (request.method !== "POST" || request.url !== "/restart") {
      writeJson(response, 404, { error: "not found" })
      return
    }
    if (restarting || shuttingDown) {
      writeJson(response, 409, { error: "backend restart already in progress" })
      return
    }

    restarting = true
    try {
      const body = await readJsonBody(request)
      const offlineMilliseconds = boundedInteger(
        body?.offline_milliseconds,
        0,
        10_000,
      )
      await stopBackend(backend)
      if (offlineMilliseconds > 0) await delay(offlineMilliseconds)
      backend = spawnBackend()
      watchBackend()
      await waitForBackendHealth()
      writeJson(response, 200, { restarted: true })
    } catch (error) {
      writeJson(response, 500, {
        error: error instanceof Error ? error.message : String(error),
      })
    } finally {
      restarting = false
    }
  })
  await new Promise((resolve, reject) => {
    control.once("error", reject)
    control.listen(controlPort, "127.0.0.1", resolve)
  })

  const forwardSignal = (signal) => {
    shuttingDown = true
    control.close()
    if (!backend.killed) backend.kill(signal)
  }

  process.on("SIGINT", forwardSignal)
  process.on("SIGTERM", forwardSignal)

  const watchBackend = () => {
    backend.once("exit", (code, signal) => {
      if (restarting) return
      if (shuttingDown) {
        process.exit(0)
        return
      }
      console.error(
        `backend exited unexpectedly (${signal ?? `code ${code ?? "unknown"}`})`,
      )
      process.exit(1)
    })
    backend.once("error", (error) => {
      console.error(error)
      if (!restarting && !shuttingDown) process.exit(1)
    })
  }
  watchBackend()
}

function spawnBackend() {
  return spawn(
    pythonExecutable,
    [
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
}

async function stopBackend(backend) {
  if (backend.exitCode !== null || backend.signalCode !== null) return
  const exited = new Promise((resolve) => backend.once("exit", resolve))
  backend.kill("SIGTERM")
  const graceful = await Promise.race([
    exited.then(() => true),
    delay(10_000).then(() => false),
  ])
  if (graceful) return
  backend.kill("SIGKILL")
  await exited
}

async function waitForBackendHealth() {
  const deadline = Date.now() + 20_000
  const healthUrl = `http://127.0.0.1:${backendPort}/api/v1/system/health`
  while (Date.now() < deadline) {
    try {
      const response = await fetch(healthUrl)
      if (response.ok) return
    } catch {
      // The socket is expected to refuse connections while uvicorn starts.
    }
    await delay(100)
  }
  throw new Error("restarted backend did not become healthy")
}

function readJsonBody(request) {
  return new Promise((resolve, reject) => {
    let body = ""
    request.setEncoding("utf8")
    request.on("data", (chunk) => {
      body += chunk
    })
    request.on("end", () => {
      try {
        resolve(body ? JSON.parse(body) : {})
      } catch (error) {
        reject(error)
      }
    })
    request.on("error", reject)
  })
}

function boundedInteger(value, minimum, maximum) {
  if (!Number.isInteger(value)) return minimum
  return Math.max(minimum, Math.min(maximum, value))
}

function writeJson(response, status, body) {
  response.writeHead(status, { "content-type": "application/json" })
  response.end(JSON.stringify(body))
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds))
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
