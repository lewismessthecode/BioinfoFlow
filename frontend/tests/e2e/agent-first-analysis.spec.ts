import { expect, test } from "@playwright/test"

import { AgentPage } from "./pages/agent-page"
import { Sidebar } from "./pages/sidebar"

test.describe("Agent first analysis journey", () => {
  test("creates a project and completes the first analysis turn with the deterministic agent runtime", async ({
    page,
  }, testInfo) => {
    const agent = new AgentPage(page)
    const sidebar = new Sidebar(page)
    const projectName = `Agent First Analysis ${testInfo.retry}`
    const prompt = "Inspect this workspace and tell me what you find."

    await agent.goto()
    await sidebar.expectLoaded()
    await sidebar.createProject(projectName, "Agent first-analysis coverage")
    await sidebar.selectProject(projectName)

    await agent.expectComposerReady()
    await agent.sendMessage(prompt)

    await expect(page.getByText(prompt)).toBeVisible()
    await expect(sidebar.root.getByRole("button", { name: prompt, exact: true })).toBeVisible({
      timeout: 30_000,
    })
    await expect(
      page.getByText("I scanned the workspace and I'm ready to proceed.")
    ).toBeVisible({ timeout: 30_000 })
    await expect(page.getByRole("button", { name: /Used \d+ tools/ })).toBeVisible({
      timeout: 30_000,
    })
  })
})
