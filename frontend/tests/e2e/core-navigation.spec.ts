import { test } from "@playwright/test"
import { AgentPage } from "./pages/agent-page"
import { RunsPage } from "./pages/runs-page"
import { WorkflowsPage } from "./pages/workflows-page"
import { ImagesPage } from "./pages/images-page"

test.describe("Core navigation journey", () => {
  test("loads the core app routes in dev auth mode", async ({ page }) => {
    const agent = new AgentPage(page)
    await agent.goto()
    await agent.expectLoaded()

    const runs = new RunsPage(page)
    await runs.goto()
    await runs.expectLoaded()

    await page.goto("/workflows")
    const workflows = new WorkflowsPage(page)
    await workflows.expectLoaded()

    const images = new ImagesPage(page)
    await images.goto()
    await images.expectLoaded()
  })
})
