import path from "node:path"
import { defineConfig, devices } from "@playwright/test"

const frontendPort = Number(process.env.PLAYWRIGHT_FRONTEND_PORT || 3100)
const backendPort = Number(process.env.PLAYWRIGHT_BACKEND_PORT || 8100)
const authMode = process.env.PLAYWRIGHT_AUTH_MODE || "dev"
const e2eStateRoot = path.resolve(process.cwd(), ".playwright-e2e", "run-lifecycle")
const bioinfoflowHome = path.join(e2eStateRoot, "bioinfoflow-home")
const betterAuthDbPath = path.join(bioinfoflowHome, "state", "auth", "better-auth.db")
const baseURL = process.env.BASE_URL || `http://127.0.0.1:${frontendPort}`
const apiBaseUrl = `http://127.0.0.1:${backendPort}/api/v1`

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  workers: 1,
  expect: { timeout: 10_000 },
  retries: process.env.CI ? 2 : 1,
  reporter: [
    ["list"],
    ["html", { outputFolder: "playwright-report", open: "never" }],
    ["junit", { outputFile: "playwright-report/results.xml" }],
  ],
  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
  webServer: [
    {
      command: `PLAYWRIGHT_BACKEND_PORT=${backendPort} node tests/e2e/support/start-backend.mjs`,
      url: `${apiBaseUrl}/system/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: [
        `AUTH_MODE=${authMode}`,
        `NEXT_PUBLIC_AUTH_MODE=${authMode}`,
        `NEXT_PUBLIC_API_BASE_URL=${apiBaseUrl}`,
        `BIOINFOFLOW_HOME=${bioinfoflowHome}`,
        `BETTER_AUTH_DB_PATH=${betterAuthDbPath}`,
        `BETTER_AUTH_URL=${baseURL}`,
        `bun run dev -- --hostname 127.0.0.1 --port ${frontendPort} --webpack`,
      ].join(" "),
      url: `${baseURL}/runs`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
})
