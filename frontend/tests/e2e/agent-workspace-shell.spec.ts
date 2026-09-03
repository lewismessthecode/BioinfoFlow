import { expect, test, type APIRequestContext, type Page, type TestInfo } from "@playwright/test"

import { disableKeylessAgentProviders } from "./support/keyless-agent"

const backendPort = Number(process.env.PLAYWRIGHT_BACKEND_PORT || 8100)
const apiBaseUrl = `http://127.0.0.1:${backendPort}/api/v1`

async function createShellProject(
  request: APIRequestContext,
  testInfo: TestInfo,
): Promise<{ id: string; name: string }> {
  const suffix = [
    testInfo.project.name,
    testInfo.workerIndex,
    testInfo.retry,
    Date.now(),
  ].join("-")
  const name = `Agent shell ${suffix}`
  const response = await request.post(`${apiBaseUrl}/projects`, {
    data: {
      name,
      description: "Project created for agent shell characterization",
    },
  })
  await expect(response).toBeOK()
  const payload = (await response.json()) as { data: { id: string } }
  return { id: payload.data.id, name }
}

async function openAgentShell(page: Page, projectId: string): Promise<void> {
  await page.addInitScript((id) => {
    window.localStorage.setItem("bioinfoflow:last-used-project", id)
  }, projectId)
  await page.goto("/agent")
  await expect(page.getByTestId("agent-page-shell")).toBeVisible()
  await expect(
    page.getByRole("button", { name: "Open terminal", exact: true }),
  ).toBeVisible()
}

test.describe("Agent workspace shell", () => {
  test("keeps navigation, panel, terminal, and responsive contracts stable", async ({
    page,
    request,
  }, testInfo) => {
    await disableKeylessAgentProviders(request)
    const project = await createShellProject(request, testInfo)
    await openAgentShell(page, project.id)

    await expect(page.getByTestId("navbar-action-row")).toBeVisible()
    await expect(
      page.getByRole("button", { name: "More preferences", exact: true }),
    ).toBeVisible()
    await expect(
      page.getByRole("button", { name: "Open workspace panel", exact: true }),
    ).toBeVisible()
    await expect(page.getByText(/Subagents/i)).toHaveCount(0)
    const viewport = page.viewportSize()
    if (!viewport) throw new Error("Agent shell screenshot requires a viewport")
    await expect(page).toHaveScreenshot(
      `agent-workspace-shell-${viewport.width}x${viewport.height}.png`,
      {
        animations: "disabled",
        caret: "hide",
        mask: [
          page.locator("#sidebar-workspace-tree"),
          page.getByText(project.name, { exact: true }),
        ],
        maskColor: "#ff00ff",
      },
    )

    const isMobile = (page.viewportSize()?.width ?? 0) < 768
    const workspaceButton = page.getByRole("button", {
      name: "Open workspace panel",
      exact: true,
    })
    await workspaceButton.focus()
    await expect(workspaceButton).toBeFocused()
    await page.keyboard.press("Enter")

    const liveDeck = page.getByRole("complementary", {
      name: "Live workspace information",
    })
    await expect(liveDeck).toBeVisible()
    for (const tabName of ["Files", "Workflow", "Artifacts", "Browser"]) {
      await expect(liveDeck.getByRole("tab", { name: tabName })).toBeVisible()
    }
    await expect(liveDeck.getByRole("tab", { name: "Files" })).toHaveAttribute(
      "data-state",
      "active",
    )
    await liveDeck.getByRole("tab", { name: "Artifacts" }).click()
    await expect(
      liveDeck.getByRole("tab", { name: "Artifacts" }),
    ).toHaveAttribute("data-state", "active")

    if (isMobile) {
      await expect(page.getByRole("dialog")).toBeVisible()
      await page.reload()
      await expect(liveDeck).toBeVisible()
      await expect(
        liveDeck.getByRole("tab", { name: "Artifacts" }),
      ).toHaveAttribute("data-state", "active")
      await page.getByRole("button", { name: "Hide panel", exact: true }).click()
      await expect(liveDeck).toHaveCount(0)
    } else {
      await expect(
        page.getByRole("button", { name: "Close workspace panel", exact: true }),
      ).toBeVisible()
      await page
        .getByRole("button", { name: "Close workspace panel", exact: true })
        .click()
      await expect(liveDeck).toHaveCount(0)

      await workspaceButton.click()
      await expect(liveDeck).toBeVisible()
      await page.reload()
      await expect(
        page.getByRole("button", { name: "Close workspace panel", exact: true }),
      ).toBeVisible()
      await expect(liveDeck).toBeVisible()
    }

    await page.getByRole("button", { name: "Open terminal", exact: true }).click()
    await expect(page.getByTestId("terminal-dock-tab")).toBeVisible()
    await expect(page.getByTestId("terminal-dock-viewport")).toBeVisible()
    await page.getByRole("button", { name: "Close terminal", exact: true }).click()
    await expect(page.getByTestId("terminal-dock-tab")).toHaveCount(0)

    if (isMobile) {
      await page.getByRole("button", { name: "Open workspace panel", exact: true }).click()
      await expect(liveDeck).toBeVisible()
      await page.getByRole("button", { name: "Hide panel", exact: true }).click()
      await expect(liveDeck).toHaveCount(0)
    }
  })
})
