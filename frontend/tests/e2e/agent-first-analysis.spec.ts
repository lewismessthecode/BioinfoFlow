import { expect, test } from "@playwright/test"

import { AgentPage } from "./pages/agent-page"
import { Sidebar } from "./pages/sidebar"

test.describe("Agent first analysis journey", () => {
  test("activates the demo and submits the seeded workflow through the guarded Agent path", async ({
    page,
  }) => {
    const agent = new AgentPage(page)
    const sidebar = new Sidebar(page)
    const prompt = "Check and run the demo workflow"
    const backendPort = Number(process.env.PLAYWRIGHT_BACKEND_PORT || 8100)
    const modelPort = Number(process.env.PLAYWRIGHT_MODEL_PORT || 9100)
    const apiBaseUrl = `http://127.0.0.1:${backendPort}/api/v1`
    const runRequests: string[] = []
    page.on("request", (request) => {
      if (request.method() === "POST" && request.url().includes("/api/v1/runs")) {
        runRequests.push(request.url())
      }
    })

    const providerSetup = await page.request.post(`${apiBaseUrl}/llm/provider-setups`, {
      data: {
        template_id: "openai-compatible",
        name: "E2E run approval model",
        base_url: `http://127.0.0.1:${modelPort}/v1`,
        wire_protocol: "chat_completions",
        api_key: "e2e-test-key",
        model_ids: ["e2e-runs-submit"],
        discover: false,
        enabled: true,
        allow_insecure_http: true,
      },
    })
    expect(providerSetup.ok()).toBe(true)

    const bootstrapResponsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        /\/api\/v1\/first-run\/bootstrap$/.test(response.url()),
    )
    await agent.goto()
    const bootstrapResponse = await bootstrapResponsePromise
    expect(bootstrapResponse.ok()).toBe(true)
    await expect(bootstrapResponse.json()).resolves.toMatchObject({
      success: true,
      data: {
        ready: true,
        created: true,
        demo_project_id: expect.any(String),
        workflow_id: expect.any(String),
      },
    })
    await sidebar.expectLoaded()
    await expect(
      sidebar.root.getByRole("button", { name: "Bioinfoflow Demo", exact: true }),
    ).toBeVisible()
    await agent.expectComposerReady()
    const breadcrumbs = page.getByRole("navigation", { name: "Breadcrumbs" })
    const actionRow = page.getByTestId("navbar-action-row")

    await page.setViewportSize({ width: 768, height: 720 })
    await expect(breadcrumbs).toBeVisible()
    await expect(breadcrumbs).toContainText("Bioinfoflow Demo")
    await expect(actionRow).toBeVisible()
    const breadcrumbBounds = await breadcrumbs.boundingBox()
    const actionRowBounds = await actionRow.boundingBox()
    expect(breadcrumbBounds).not.toBeNull()
    expect(actionRowBounds).not.toBeNull()
    expect(breadcrumbBounds!.x + breadcrumbBounds!.width).toBeLessThanOrEqual(
      actionRowBounds!.x,
    )
    const navbarActionCount = await actionRow.locator("button").count()
    expect(navbarActionCount).toBeGreaterThan(0)

    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 720 })
      await expect(breadcrumbs).toBeHidden()
      await expect(actionRow.locator("button")).toHaveCount(navbarActionCount)
      for (let index = 0; index < navbarActionCount; index += 1) {
        await expect(actionRow.locator("button").nth(index)).toBeVisible()
      }

      const layout = await page.evaluate(() => {
        const navbar = document.querySelector("header")
        const actionRow = document.querySelector<HTMLElement>(
          '[data-testid="navbar-action-row"]',
        )
        const actionBounds = actionRow
          ? Array.from(actionRow.querySelectorAll<HTMLElement>("button")).map(
              (button) => {
                const rect = button.getBoundingClientRect()
                return { left: rect.left, right: rect.right }
              },
            )
          : []
        return {
          overflow: {
            document:
              document.documentElement.scrollWidth -
              document.documentElement.clientWidth,
            body: document.body.scrollWidth - document.body.clientWidth,
            navbar: navbar ? navbar.scrollWidth - navbar.clientWidth : null,
          },
          actionBounds,
        }
      })

      expect(layout.overflow, `${width}px viewport overflow`).toEqual({
        document: 0,
        body: 0,
        navbar: 0,
      })
      expect(layout.actionBounds.length).toBeGreaterThan(0)
      for (const bounds of layout.actionBounds) {
        expect(bounds.left, `${width}px action left edge`).toBeGreaterThanOrEqual(0)
        expect(bounds.right, `${width}px action right edge`).toBeLessThanOrEqual(width)
      }
      await expect(agent.messageInput).toBeVisible()
      await expect(agent.sendButton).toBeVisible()
    }
    await page.setViewportSize({ width: 1280, height: 720 })

    const primaryStarter = page.getByRole("button", { name: prompt, exact: true })
    await expect(primaryStarter).toBeVisible()
    const sessionRequestPromise = page.waitForRequest(
      (request) =>
        request.method() === "POST" &&
        /\/api\/v1\/agent\/sessions$/.test(request.url()),
    )
    const turnRequestPromise = page.waitForRequest(
      (request) =>
        request.method() === "POST" &&
        /\/api\/v1\/agent\/sessions\/[^/]+\/turns$/.test(request.url()),
    )

    await primaryStarter.click()

    const sessionRequest = await sessionRequestPromise
    const sessionPayload = sessionRequest.postDataJSON()
    expect(sessionPayload.permission_mode).toBe("guarded_auto")
    expect(sessionPayload.automation_mode).toBe("assisted")

    const turnRequest = await turnRequestPromise
    const turnPayload = turnRequest.postDataJSON()
    expect(turnPayload.input_text).toBe(prompt)
    expect(turnPayload.input_parts).toEqual([
      { type: "text", text: prompt },
      {
        kind: "workflow_ref",
        workflow_id: expect.any(String),
        project_id: expect.any(String),
        scope: "project",
      },
    ])

    await expect(page.getByText(prompt)).toBeVisible()
    const approvalCard = page.getByTestId("inline-approval-card")
    await expect(approvalCard).toBeVisible({ timeout: 30_000 })
    await expect(approvalCard.getByText("runs.submit")).toBeVisible()
    await expect(approvalCard.getByRole("button", { name: "Approve" })).toBeVisible()
    await expect(approvalCard.getByRole("button", { name: "Reject" })).toBeVisible()
    expect(runRequests).toEqual([])

    const runsResponse = await page.request.get(`${apiBaseUrl}/runs`, {
      params: { limit: 20 },
    })
    expect(runsResponse.ok()).toBe(true)
    await expect(runsResponse.json()).resolves.toMatchObject({ data: [] })
  })
})
