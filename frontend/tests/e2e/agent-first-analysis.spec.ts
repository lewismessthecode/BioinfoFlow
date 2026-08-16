import { expect, test } from "@playwright/test"

import { AgentPage } from "./pages/agent-page"
import {
  createKeylessAgentSession,
  disableKeylessAgentProviders,
  setupKeylessAgentModel,
} from "./support/keyless-agent"

test.describe("Agent workbench live run journey", () => {
  test("keeps the draft composer centered and theme-safe on desktop and mobile", async ({
    page,
  }) => {
    await page.addInitScript(() => window.localStorage.setItem("theme", "dark"))
    await page.setViewportSize({ width: 1440, height: 900 })

    const agent = new AgentPage(page)
    await agent.goto()
    await agent.expectComposerReady()

    await expect(page.locator("html")).toHaveClass(/dark/)
    const desktopGeometry = await page.evaluate(() => {
      const workbench = document.querySelector<HTMLElement>(
        '[data-testid="agent-workbench"]',
      )
      const composer = document.querySelector<HTMLElement>(
        '[data-testid="agent-composer"]',
      )
      const surface = document.querySelector<HTMLElement>(
        '[data-testid="agent-composer-surface"]',
      )
      const textarea = composer?.querySelector("textarea")
      if (!workbench || !composer || !surface || !textarea) return null
      const workbenchBox = workbench.getBoundingClientRect()
      const composerBox = composer.getBoundingClientRect()
      return {
        centerDelta: Math.abs(
          workbenchBox.left + workbenchBox.width / 2 -
            (composerBox.left + composerBox.width / 2),
        ),
        composerWidth: composerBox.width,
        surfaceBackground: getComputedStyle(surface).backgroundColor,
        textareaBackground: getComputedStyle(textarea).backgroundColor,
      }
    })
    expect(desktopGeometry).not.toBeNull()
    expect(desktopGeometry?.centerDelta).toBeLessThan(2)
    expect(desktopGeometry?.composerWidth).toBeLessThanOrEqual(768)
    expect(desktopGeometry?.surfaceBackground).not.toBe("rgb(0, 0, 0)")
    expect(desktopGeometry?.textareaBackground).toBe("rgba(0, 0, 0, 0)")

    await page.setViewportSize({ width: 390, height: 844 })
    await page.reload()
    await agent.expectComposerReady()

    const mobileGeometry = await page.evaluate(() => {
      const composer = document.querySelector<HTMLElement>(
        '[data-testid="agent-composer"]',
      )
      if (!composer) return null
      const box = composer.getBoundingClientRect()
      return {
        left: box.left,
        right: box.right,
        viewportWidth: window.innerWidth,
        documentWidth: document.documentElement.scrollWidth,
      }
    })
    expect(mobileGeometry).not.toBeNull()
    expect(mobileGeometry?.left).toBeGreaterThanOrEqual(0)
    expect(mobileGeometry?.right).toBeLessThanOrEqual(
      mobileGeometry?.viewportWidth ?? 0,
    )
    expect(mobileGeometry?.documentWidth).toBeLessThanOrEqual(
      mobileGeometry?.viewportWidth ?? 0,
    )
  })

  test("opens inline model setup and preserves the draft when no model is available", async ({
    page,
    request,
  }) => {
    const agent = new AgentPage(page)
    const prompt = "Keep this message while I connect a model."
    await disableKeylessAgentProviders(request)

    await agent.goto()
    await agent.expectComposerReady()
    const responsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        response.url().endsWith("/api/v1/agent/sessions"),
    )
    await agent.sendMessage(prompt)

    const response = await responsePromise
    expect(response.status()).toBe(422)
    await expect
      .poll(async () => (await response.json()).error?.code)
      .toBe("AGENT_MODEL_REQUIRED")

    const dialog = page.getByRole("dialog", {
      name: "Connect a model to continue",
    })
    await expect(dialog).toBeVisible({ timeout: 20_000 })
    await expect(
      dialog.getByRole("group", { name: "OpenAI", exact: true }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(
      dialog.getByRole("link", { name: "Open full provider settings" }),
    ).toHaveAttribute("href", "/settings?section=providers")
    await expect(agent.messageInput).toHaveValue(prompt)

    await page.keyboard.press("Escape")

    await expect(dialog).toHaveCount(0)
    await expect(agent.messageInput).toHaveValue(prompt)
  })

  test("creates a Session on the first browser message", async ({
    page,
    request,
  }, testInfo) => {
    const agent = new AgentPage(page)
    await setupKeylessAgentModel(request, "streaming", testInfo)
    const prompt = "Explain the keyless browser test path."

    await agent.goto()
    await agent.expectComposerReady()
    await agent.sendMessage(prompt)
    await agent.expectSessionRoute()

    await expect(
      agent.transcript.getByText(prompt, { exact: true }),
    ).toBeVisible()
    await expect(
      agent.transcript.getByText("Keyless model stream completed.", {
        exact: true,
      }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(
      agent.transcript.getByText("Thinking", { exact: true }),
    ).toBeVisible()
  })

  test("streams thinking and the final answer through the real Agent Harness", async ({
    page,
    request,
  }, testInfo) => {
    const agent = new AgentPage(page)
    const modelId = await setupKeylessAgentModel(request, "streaming", testInfo)
    const opened = await createKeylessAgentSession(request, { modelId })
    const prompt = "Show the live keyless stream."

    await agent.gotoSession(opened.session.id)
    await agent.expectComposerReady()
    await agent.sendMessage(prompt)

    await expect(
      agent.transcript.getByText(prompt, { exact: true }),
    ).toBeVisible()
    await expect(
      agent.transcript.getByText("Thinking", { exact: true }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(
      agent.transcript.getByText("Checking the keyless request.", {
        exact: true,
      }),
    ).toBeVisible()
    await expect(
      agent.transcript.getByText("Keyless model stream completed.", {
        exact: true,
      }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(agent.activeRun).toHaveCount(0)
    const outcome = agent.transcript
      .getByTestId("agent-run-outcome")
      .filter({ hasText: "Completed" })
    await expect(outcome).toBeVisible()
  })

  test("renders a structured plan without a duplicate tool card", async ({
    page,
    request,
  }, testInfo) => {
    const agent = new AgentPage(page)
    const modelId = await setupKeylessAgentModel(request, "plan", testInfo)
    const opened = await createKeylessAgentSession(request, { modelId })

    await agent.gotoSession(opened.session.id)
    await agent.expectComposerReady()
    await agent.sendMessage("Show a plan before continuing.")

    await expect(
      agent.transcript.getByRole("heading", { name: "Keyless execution plan" }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(agent.transcript.getByText("Inspect the request")).toBeVisible()
    await expect(agent.transcript.getByText("Summarize the result")).toBeVisible()
    await expect(
      agent.transcript.getByText("The keyless plan is ready.", { exact: true }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(agent.transcript.getByText("update_plan")).toHaveCount(0)
  })

  test("groups concurrent tool calls into one parallel activity", async ({
    page,
    request,
  }, testInfo) => {
    const agent = new AgentPage(page)
    const modelId = await setupKeylessAgentModel(
      request,
      "parallel-tools",
      testInfo,
    )
    const opened = await createKeylessAgentSession(request, {
      modelId,
      permissionMode: "full_access",
    })

    await agent.gotoSession(opened.session.id)
    await agent.expectComposerReady()
    await agent.sendMessage("Inspect both environment views in parallel.")

    await expect(
      agent.transcript.getByText("Both keyless tools completed.", {
        exact: true,
      }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(agent.activityGroups).toHaveCount(1)
    await expect(
      agent.activityGroups.getByRole("button", {
        name: "2 tools running in parallel",
      }),
    ).toBeVisible()
  })

  test("labels an ordered tool batch as sequential activity", async ({
    page,
    request,
  }, testInfo) => {
    const agent = new AgentPage(page)
    const modelId = await setupKeylessAgentModel(request, "serial-tools", testInfo)
    const opened = await createKeylessAgentSession(request, {
      modelId,
      permissionMode: "full_access",
    })

    await agent.gotoSession(opened.session.id)
    await agent.expectComposerReady()
    await agent.sendMessage("Run both keyless shell inspections in sequence.")

    await expect(
      agent.transcript.getByText("Both serial tools completed.", { exact: true }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(
      agent.activityGroups.getByRole("button", {
        name: "2 tools running in sequence",
      }),
    ).toBeVisible()
  })
})
