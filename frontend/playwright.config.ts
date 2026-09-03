import { defineConfig, devices } from "@playwright/test"

const frontendPort = Number(process.env.PLAYWRIGHT_FRONTEND_PORT || 3100)
const backendPort = Number(process.env.PLAYWRIGHT_BACKEND_PORT || 8100)
const modelPort = Number(process.env.PLAYWRIGHT_MODEL_PORT || 9100)
const baseURL = process.env.BASE_URL || `http://127.0.0.1:${frontendPort}`
const apiBaseUrl = `http://127.0.0.1:${backendPort}/api/v1`
const browserApiBaseUrl = `http://localhost:${backendPort}/api/v1`
const viewportWidth = Number(process.env.PLAYWRIGHT_VIEWPORT_WIDTH)
const viewportHeight = Number(process.env.PLAYWRIGHT_VIEWPORT_HEIGHT)
const artifactDirectory =
  process.env.PLAYWRIGHT_ARTIFACT_DIRECTORY || ".playwright-e2e/artifacts"
const configuredViewport =
  Number.isInteger(viewportWidth) &&
  viewportWidth > 0 &&
  Number.isInteger(viewportHeight) &&
  viewportHeight > 0
    ? {
        width: viewportWidth,
        height: viewportHeight,
      }
    : undefined

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  workers: 1,
  expect: {
    timeout: 10_000,
    toHaveScreenshot: {
      // Keep browser and operating-system baselines explicit.
      pathTemplate:
        "{testDir}/{testFilePath}-snapshots/{arg}{-projectName}{-snapshotSuffix}{ext}",
    },
  },
  retries: process.env.CI ? 2 : 1,
  reporter: [
    ["list"],
    [
      "html",
      { outputFolder: `${artifactDirectory}/playwright-report`, open: "never" },
    ],
    ["junit", { outputFile: `${artifactDirectory}/results.xml` }],
  ],
  outputDir: `${artifactDirectory}/test-results`,
  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        ...(configuredViewport ? { viewport: configuredViewport } : {}),
      },
    },
    { name: "firefox", use: { ...devices["Desktop Firefox"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
  webServer: [
    {
      command: `PLAYWRIGHT_MODEL_PORT=${modelPort} node tests/e2e/support/mock-openai-server.mjs`,
      url: `http://127.0.0.1:${modelPort}/v1/models`,
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: `PLAYWRIGHT_BACKEND_PORT=${backendPort} node tests/e2e/support/start-backend.mjs`,
      url: `${apiBaseUrl}/system/health`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `AUTH_MODE=dev NEXT_PUBLIC_AUTH_MODE=dev NEXT_PUBLIC_API_BASE_URL=${browserApiBaseUrl} bun run build && cp -R .next/static .next/standalone/.next/static && AUTH_MODE=dev NEXT_PUBLIC_AUTH_MODE=dev NEXT_PUBLIC_API_BASE_URL=${browserApiBaseUrl} HOSTNAME=127.0.0.1 PORT=${frontendPort} node .next/standalone/server.js`,
      url: `${baseURL}/runs`,
      reuseExistingServer: false,
      timeout: 240_000,
    },
  ],
})
