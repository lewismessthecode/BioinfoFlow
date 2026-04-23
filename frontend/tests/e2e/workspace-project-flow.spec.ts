import { expect, test } from "@playwright/test"
import { AgentPage } from "./pages/agent-page"
import { Sidebar } from "./pages/sidebar"

test.describe("Workspace project journey", () => {
  test("creates a project from the empty workspace and switches page context to it", async ({ page }, testInfo) => {
    const agent = new AgentPage(page)
    const sidebar = new Sidebar(page)
    const projectName = `E2E Project Alpha ${testInfo.retry}`

    await agent.goto()
    await sidebar.expectLoaded()
    await expect(page.getByText("Select a project")).toBeVisible()

    await sidebar.createProject(projectName, "Browser-created workspace context")
    await expect(sidebar.projectButton(projectName)).toBeVisible()

    await sidebar.selectProject(projectName)

    await expect(page.getByLabel("Breadcrumbs")).toContainText(projectName)
    await expect(page.getByRole("button", { name: "Open terminal" })).toBeVisible()
    await expect(page.getByText("Select a project")).not.toBeVisible()
  })
})
