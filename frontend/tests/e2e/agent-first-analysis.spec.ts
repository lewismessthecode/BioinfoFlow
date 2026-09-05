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
      const send = document.querySelector<HTMLElement>(
        '[data-testid="agent-composer-send"]',
      )
      const textarea = composer?.querySelector("textarea")
      if (!workbench || !composer || !surface || !send || !textarea) return null
      const workbenchBox = workbench.getBoundingClientRect()
      const composerBox = composer.getBoundingClientRect()
      const starterList = document.querySelector<HTMLElement>(
        '[data-testid="agent-starter-prompt-list"]',
      )
      const commandHint = document.querySelector<HTMLElement>(
        '[data-testid="agent-command-discovery-hint"]',
      )
      const surfaceStyle = getComputedStyle(surface)
      const sendStyle = getComputedStyle(send)
      const sendBox = send.getBoundingClientRect()
      const workbenchStyle = getComputedStyle(workbench)
      const selectorMetrics = Array.from(
        composer.querySelectorAll<HTMLElement>(
          '[data-composer-selector-trigger="true"]',
        ),
      ).map((selector) => {
        const selectorBox = selector.getBoundingClientRect()
        const icon = selector.querySelector<HTMLElement>(
          '[data-composer-selector-slot="icon"]',
        )
        const text = selector.querySelector<HTMLElement>(
          '[data-composer-selector-slot="text"]',
        )
        const chevron = selector.querySelector<HTMLElement>(
          '[data-composer-selector-slot="chevron"]',
        )
        const textBox = text?.getBoundingClientRect()
        const style = getComputedStyle(selector)
        return {
          height: selectorBox.height,
          fontSize: style.fontSize,
          lineHeight: style.lineHeight,
          textTop: textBox ? textBox.top - selectorBox.top : null,
          iconSize: icon
            ? [icon.getBoundingClientRect().width, icon.getBoundingClientRect().height]
            : null,
          textHeight: textBox?.height ?? null,
          chevronSize: chevron
            ? [
                chevron.getBoundingClientRect().width,
                chevron.getBoundingClientRect().height,
              ]
            : null,
        }
      })
      return {
        centerDelta: Math.abs(
          workbenchBox.left + workbenchBox.width / 2 -
            (composerBox.left + composerBox.width / 2),
        ),
        composerWidth: composerBox.width,
        composerHeight: surface.getBoundingClientRect().height,
        selectorMetrics,
        starterBorderTop: starterList
          ? getComputedStyle(starterList).borderTopWidth
          : null,
        starterBorderBottom: starterList
          ? getComputedStyle(starterList).borderBottomWidth
          : null,
        surfaceBackground: surfaceStyle.backgroundColor,
        surfaceShadow: surfaceStyle.boxShadow,
        canvasBackground: workbenchStyle.backgroundColor,
        surfaceBorderWidth: surfaceStyle.borderTopWidth,
        sendSize: [sendBox.width, sendBox.height],
        sendRadius: Number.parseFloat(sendStyle.borderRadius),
        textareaBackground: getComputedStyle(textarea).backgroundColor,
        hintBottomInset: commandHint
          ? window.innerHeight - commandHint.getBoundingClientRect().bottom
          : null,
      }
    })
    expect(desktopGeometry).not.toBeNull()
    expect(desktopGeometry?.centerDelta).toBeLessThan(2)
    expect(desktopGeometry?.composerWidth).toBeLessThanOrEqual(672)
    expect(desktopGeometry?.composerHeight).toBe(138)
    expect(desktopGeometry?.selectorMetrics).toHaveLength(3)
    expect(
      new Set(desktopGeometry?.selectorMetrics.map(({ height }) => height)).size,
    ).toBe(1)
    expect(desktopGeometry?.selectorMetrics[0]?.height).toBe(32)
    expect(
      new Set(desktopGeometry?.selectorMetrics.map(({ fontSize }) => fontSize)).size,
    ).toBe(1)
    expect(
      new Set(desktopGeometry?.selectorMetrics.map(({ lineHeight }) => lineHeight))
        .size,
    ).toBe(1)
    expect(
      new Set(desktopGeometry?.selectorMetrics.map(({ textTop }) => textTop)).size,
    ).toBe(1)
    for (const metrics of desktopGeometry?.selectorMetrics ?? []) {
      expect(metrics.iconSize).toEqual([16, 16])
      expect(metrics.textHeight).toBe(16)
      if (metrics.chevronSize) expect(metrics.chevronSize).toEqual([16, 16])
    }
    expect(
      desktopGeometry?.selectorMetrics.filter(({ chevronSize }) => chevronSize)
        .length,
    ).toBeGreaterThanOrEqual(2)
    expect(desktopGeometry?.starterBorderTop).toBe("0px")
    expect(desktopGeometry?.starterBorderBottom).toBe("0px")
    expect(desktopGeometry?.surfaceBackground).not.toBe("rgb(0, 0, 0)")
    expect(desktopGeometry?.surfaceBackground).not.toBe(
      desktopGeometry?.canvasBackground,
    )
    expect(desktopGeometry?.surfaceBorderWidth).toBe("1px")
    expect(desktopGeometry?.surfaceShadow).not.toBe("none")
    expect(desktopGeometry?.sendSize).toEqual([32, 32])
    expect(desktopGeometry?.sendRadius).toBeGreaterThanOrEqual(16)
    expect(desktopGeometry?.textareaBackground).toBe("rgba(0, 0, 0, 0)")
    expect(desktopGeometry?.hintBottomInset).toBeGreaterThanOrEqual(40)
    await expect(
      page.getByRole("heading", {
        name: "Ready when you are.",
      }),
    ).toBeVisible()
    await expect(
      page.getByText("Ask a question, attach data, or reference a workflow."),
    ).toHaveCount(0)
    await expect(page.getByTestId("agent-capability-hint")).toHaveCount(0)
    await expect(
      page.getByText("Try a project-aware starting point"),
    ).toHaveCount(0)
    await expect(page.locator("[data-starter-slot-icon]")).toHaveCount(3)
    const starterIconSurfaces = await page
      .locator("[data-starter-slot-icon]")
      .evaluateAll((icons) =>
        icons.map((icon) => {
          const style = getComputedStyle(icon)
          return {
            background: style.backgroundColor,
            border: style.borderWidth,
            radius: style.borderRadius,
          }
        }),
      )
    expect(starterIconSurfaces).toEqual([
      { background: "rgba(0, 0, 0, 0)", border: "0px", radius: "0px" },
      { background: "rgba(0, 0, 0, 0)", border: "0px", radius: "0px" },
      { background: "rgba(0, 0, 0, 0)", border: "0px", radius: "0px" },
    ])
    const commandHint = page.getByTestId("agent-command-discovery-hint")
    await expect(commandHint).toContainText("/")
    await expect(commandHint).toContainText("skill")
    await expect
      .poll(async () => commandHint.textContent(), { timeout: 7_000 })
      .toContain("@")
    await expect(
      page.getByRole("button", {
        name: /^Execution environments: Auto, All environments$/,
      }),
    ).toBeVisible()

    const permissionButton = page.getByRole("button", {
      name: "Approval: Confirm risks",
    })
    await permissionButton.click()
    const permissionMenu = page.getByTestId("composer-selector-menu")
    await expect(permissionMenu).toBeVisible()
    await expect
      .poll(() =>
        permissionMenu.evaluate((menu) => getComputedStyle(menu).width),
      )
      .toBe("244px")
    await page.keyboard.press("Escape")

    const filesButton = page.getByRole("button", {
      name: "Files",
    })
    await expect(filesButton).toBeVisible()
    await expect(page.getByRole("button", { name: "Open terminal" })).toBeVisible()
    const navbarActionGeometry = await page.evaluate(() => {
      const row = document.querySelector<HTMLElement>(
        '[data-testid="navbar-action-row"]',
      )
      const canvas = document.querySelector<HTMLElement>(
        '[data-testid="agent-workbench"]',
      )
      if (!row || !canvas) return null
      const actionButtons = Array.from(
        row.querySelectorAll<HTMLElement>("[data-action-id]"),
      )
      const boxes = actionButtons.map((button) => button.getBoundingClientRect())
      return {
        actionIds: actionButtons.map((button) => button.dataset.actionId),
        actionOwnedByNavbar: actionButtons.every(
          (button) => row.contains(button),
        ),
        actionSizes: boxes.map(({ width, height }) => [width, height]),
        actionGaps: boxes.slice(1).map(
          (box, index) => box.left - boxes[index].right,
        ),
        navbarGap: Number.parseFloat(getComputedStyle(row).columnGap),
        actionsInsideCanvas: actionButtons.some((button) => canvas.contains(button)),
      }
    })
    expect(navbarActionGeometry?.actionIds).toEqual([
      "artifacts",
      "files",
      "dag",
      "browser",
    ])
    expect(navbarActionGeometry?.actionOwnedByNavbar).toBe(true)
    expect(
      navbarActionGeometry?.actionSizes.every(
        ([width, height]) => width >= 32 && width <= 120 && height >= 32 && height <= 36,
      ),
    ).toBe(true)
    expect(navbarActionGeometry?.actionGaps).toEqual([2, 2, 2])
    expect(navbarActionGeometry?.navbarGap).toBe(6)
    expect(navbarActionGeometry?.actionsInsideCanvas).toBe(false)
    await filesButton.click()
    const liveDeck = page.getByRole("complementary", {
      name: "Live workspace information",
    })
    await expect(liveDeck).toBeVisible()
    await expect(
      liveDeck.getByRole("region", { name: "Project file browser" }),
    ).toBeVisible()
    await expect(liveDeck.getByTestId("live-deck-tab-bar")).toHaveCount(0)
    await expect(liveDeck.getByRole("tab")).toHaveCount(0)
    await expect(
      liveDeck.getByRole("button", { name: "Hide panel", exact: true }),
    ).toHaveCount(0)

    await page.setViewportSize({ width: 390, height: 844 })
    await page.reload()
    await agent.expectComposerReady()

    const mobileGeometry = await page.evaluate(() => {
      const composer = document.querySelector<HTMLElement>(
        '[data-testid="agent-composer"]',
      )
      const send = composer?.querySelector<HTMLElement>(
        '[data-testid="agent-composer-send"]',
      )
      if (!composer || !send) return null
      const box = composer.getBoundingClientRect()
      const sendBox = send.getBoundingClientRect()
      return {
        left: box.left,
        right: box.right,
        viewportWidth: window.innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        selectorHeights: Array.from(
          composer.querySelectorAll<HTMLElement>(
            '[data-composer-selector-trigger="true"]',
          ),
        ).map((selector) => selector.getBoundingClientRect().height),
        sendSize: [sendBox.width, sendBox.height],
        sendRadius: Number.parseFloat(getComputedStyle(send).borderRadius),
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
    expect(mobileGeometry?.selectorHeights).toHaveLength(3)
    expect(new Set(mobileGeometry?.selectorHeights).size).toBe(1)
    expect(mobileGeometry?.selectorHeights[0]).toBeGreaterThanOrEqual(44)
    expect(mobileGeometry?.sendSize).toEqual([44, 44])
    expect(mobileGeometry?.sendRadius).toBeGreaterThanOrEqual(22)
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
    await expect(page.getByTestId("agent-header-model")).toHaveCount(0)
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
    await expect(agent.transcript.getByTestId("agent-run-outcome")).toHaveCount(0)
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

    await page.getByRole("button", { name: "Expand plan", exact: true }).click()
    const planCard = page.getByTestId("agent-plan-card")
    await expect(
      planCard.getByRole("heading", { name: "Keyless execution plan" }),
    ).toBeVisible({ timeout: 20_000 })
    await expect(planCard.getByText("Inspect the request")).toBeVisible()
    await expect(planCard.getByText("Summarize the result")).toBeVisible()
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
    const rows = agent.activityGroups.locator("[data-agent-activity-row]")
    await expect(rows).toHaveCount(2)
    await expect(agent.activityGroups).not.toContainText(/tools running/i)
    expect(
      await rows.first().evaluate((row) => row.getBoundingClientRect().height),
    ).toBeLessThanOrEqual(36)
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
    await expect(agent.activityGroups).toHaveCount(1)
    await expect(
      agent.activityGroups.locator("[data-agent-activity-row]"),
    ).toHaveCount(2)
    await expect(agent.activityGroups).not.toContainText(/tools running/i)
  })
})
