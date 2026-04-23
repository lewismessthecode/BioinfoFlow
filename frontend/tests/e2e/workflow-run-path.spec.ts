import path from "node:path"
import { expect, test } from "@playwright/test"
import { AgentPage } from "./pages/agent-page"
import { Sidebar } from "./pages/sidebar"
import { WorkflowsPage } from "./pages/workflows-page"

const workflowFixturePath = path.resolve(process.cwd(), "tests/e2e/fixtures/e2e-workflow.nf")

test.describe("Workflow registration and run journey", () => {
  test("registers a local workflow and surfaces the new run in Runs", async ({ page }, testInfo) => {
    const agent = new AgentPage(page)
    const sidebar = new Sidebar(page)
    const workflows = new WorkflowsPage(page)
    const projectName = `Workflow Run Project ${testInfo.retry}`
    const workflowName = `e2e-workflow-${testInfo.retry}`

    await agent.goto()
    await sidebar.expectLoaded()
    await sidebar.createProject(projectName, "Workflow registration and run coverage")

    await page.getByRole("link", { name: "Workflows", exact: true }).click()
    await workflows.expectLoaded()

    await page.getByRole("tab", { name: "Hub", exact: true }).click()
    await page.getByRole("button", { name: "Register Workflow", exact: true }).last().click()

    const registerDialog = page.getByRole("dialog")
    await registerDialog.getByRole("button", { name: "Local", exact: true }).click()
    await registerDialog.getByRole("button", { name: "Single file", exact: true }).click()
    await registerDialog.getByLabel("Workflow File (.nf or .wdl)").setInputFiles(workflowFixturePath)
    await registerDialog.getByLabel("Workflow Name (optional)").fill(workflowName)
    await registerDialog.getByRole("button", { name: "Register Workflow", exact: true }).click()

    await expect(page.getByText(`Workflow "${workflowName}" registered`)).toBeVisible()

    await workflows.searchInput.fill(workflowName)
    await page.getByRole("button", { name: "List view", exact: true }).click()

    const workflowRow = page.locator("tbody tr").filter({ hasText: workflowName })
    const runResponsePromise = page.waitForResponse((response) => {
      return response.request().method() === "POST" && response.url().includes("/api/v1/runs")
    })

    await workflowRow.getByRole("button", { name: "Run", exact: true }).click()
    await expect(page.getByRole("button", { name: "Submit Run", exact: true })).toBeEnabled({
      timeout: 30_000,
    })
    await page.getByRole("button", { name: "Submit Run", exact: true }).click()

    const runResponse = await runResponsePromise
    const runPayload = (await runResponse.json()) as {
      data: { run_id: string }
    }
    const runId = runPayload.data.run_id

    await expect(page).toHaveURL(/\/runs\?/)
    await expect(page.getByRole("heading", { name: "Runs" })).toBeVisible()
    await expect(page.locator('tbody > tr[role="button"]').filter({ hasText: runId })).toBeVisible({
      timeout: 30_000,
    })
  })
})
