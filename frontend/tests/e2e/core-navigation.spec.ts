import { test } from "@playwright/test"
import { AgentPage } from "./pages/agent-page"
import { RunsPage } from "./pages/runs-page"
import { WorkflowsPage } from "./pages/workflows-page"
import { ImagesPage } from "./pages/images-page"

test.describe("Core navigation journey", () => {
  test("Agent -> Runs -> Workflows -> Images", async ({ page }) => {
    const agent = new AgentPage(page)
    await agent.goto()
    await agent.expectLoaded()

    await agent.goToRuns()
    const runs = new RunsPage(page)
    await runs.expectLoaded()

    await runs.goToWorkflows()
    const workflows = new WorkflowsPage(page)
    await workflows.expectLoaded()

    await workflows.goToImages()
    const images = new ImagesPage(page)
    await images.expectLoaded()
  })
})
