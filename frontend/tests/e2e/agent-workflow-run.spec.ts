import path from "node:path"
import { expect, test } from "@playwright/test"

import { AgentPage } from "./pages/agent-page"
import { RunsPage } from "./pages/runs-page"
import { Sidebar } from "./pages/sidebar"
import { WorkflowsPage } from "./pages/workflows-page"

const workflowFixturePath = path.resolve(process.cwd(), "tests/e2e/fixtures/e2e-workflow.nf")

test.describe("Agent workflow-run journey", () => {
  test("registers a project workflow, approves the agent run, and sees the queued run in Runs", async ({
    page,
  }, testInfo) => {
    const agent = new AgentPage(page)
    const runs = new RunsPage(page)
    const sidebar = new Sidebar(page)
    const workflows = new WorkflowsPage(page)
    const projectName = `Agent Workflow Project ${testInfo.retry}`
    const workflowName = `agent-e2e-workflow-${testInfo.retry}`
    const prompt = `Please run the ${workflowName} workflow for this project.`

    await agent.goto()
    await sidebar.expectLoaded()
    await sidebar.createProject(projectName, "Agent workflow-run coverage")

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
    await workflowRow.getByRole("button", { name: "Add", exact: true }).click()
    await expect(page.getByText(`Added "${workflowName}" to project`)).toBeVisible()

    await page.getByRole("link", { name: "Agent", exact: true }).click()
    await agent.expectComposerReady()
    await agent.sendMessage(prompt)

    await expect(page.getByText(prompt)).toBeVisible()

    const approvalCard = page.getByRole("alert").filter({ hasText: "Approval required" })
    await expect(approvalCard).toContainText("platform_run_submit", { timeout: 30_000 })
    await approvalCard.getByRole("button", { name: "Approve", exact: true }).click()

    const finalMessage = page.getByText(new RegExp(`Queued run .* for workflow ${workflowName}\\.`, "i"))
    await expect(finalMessage).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText("Approved")).toBeVisible({ timeout: 30_000 })
    await expect(page.getByRole("button", { name: /Used \d+ tools/ })).toBeVisible({
      timeout: 30_000,
    })

    const finalText = await finalMessage.textContent()
    const runId = finalText?.match(/Queued run (\S+) for workflow/i)?.[1]
    expect(runId).toBeTruthy()

    await page.getByRole("link", { name: "Runs", exact: true }).click()
    await runs.expectLoaded()
    await runs.expectRunVisible(String(runId))
  })
})
