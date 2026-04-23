import path from "node:path"
import { expect, test } from "@playwright/test"
import { AgentPage } from "./pages/agent-page"
import { RunDetailPage } from "./pages/run-detail-page"
import { Sidebar } from "./pages/sidebar"
import { WorkflowsPage } from "./pages/workflows-page"

const workflowFixturePath = path.resolve(process.cwd(), "tests/e2e/fixtures/e2e-workflow.nf")

test.describe("Run detail journey", () => {
  test("opens a run from Runs and shows DAG, logs, and outputs", async ({ page }, testInfo) => {
    const agent = new AgentPage(page)
    const sidebar = new Sidebar(page)
    const workflows = new WorkflowsPage(page)
    const runDetail = new RunDetailPage(page)
    const projectName = `Run Detail Project ${testInfo.retry}`
    const workflowName = `run-detail-workflow-${testInfo.retry}`

    await agent.goto()
    await sidebar.expectLoaded()
    await sidebar.createProject(projectName, "Run detail coverage")

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
    const runRow = page.locator('tbody > tr[role="button"]').filter({ hasText: runId })
    await expect(runRow).toBeVisible({ timeout: 30_000 })
    await expect(runRow).toContainText("Completed", { timeout: 60_000 })

    await runRow.getByRole("button", { name: "View Details", exact: true }).click()
    await expect(page.getByRole("button", { name: "Open full page", exact: true })).toBeVisible()
    await page.getByRole("button", { name: "Open full page", exact: true }).click()

    await runDetail.expectLoaded(runId)
    await runDetail.expectDagVisible()
    await runDetail.expectDagNode("WRITE_HELLO")
    await runDetail.expectAnyLogs()
    await runDetail.openOutputFile(["runs", runId, "results", "hello.txt"])
    await runDetail.expectOutputPreview("hello from e2e")
  })
})
