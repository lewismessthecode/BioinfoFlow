import {
  expect,
  test,
  type APIRequestContext,
  type Page,
  type TestInfo,
} from "@playwright/test"

import { COMPACT_VIEWPORT_MAX } from "../../lib/layout-breakpoints"
import { disableKeylessAgentProviders } from "./support/keyless-agent"

const backendPort = Number(process.env.PLAYWRIGHT_BACKEND_PORT || 8100)
const apiBaseUrl = `http://127.0.0.1:${backendPort}/api/v1`
const WORKSPACE_SHEET_MAX = 1279

const SHELL_WORKSPACE_FILES = [
  {
    path: "analysis/rnaseq.wdl",
    content: [
      "version 1.0",
      "",
      "workflow rnaseq {",
      "  input {",
      "    String sample_id",
      "  }",
      "",
      "  call quantify {",
      "    input:",
      "      sample_id = sample_id",
      "  }",
      "}",
      "",
      "task quantify {",
      "  input {",
      "    String sample_id",
      "  }",
      "",
      "  command {",
      "    echo sample_id",
      "  }",
      "",
      "  output {",
      "    String result = stdout()",
      "  }",
      "}",
    ].join("\n"),
  },
  {
    path: "results/qc-report.json",
    content: [
      "{",
      '  "sample_id": "SAMPLE-001",',
      '  "qc_pass": true,',
      '  "reads": 12840',
      "}",
    ].join("\n"),
  },
  {
    path: "README.md",
    content: "# RNA-seq analysis\n\nSeeded browser evidence workspace.\n",
  },
] as const

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

async function seedShellWorkspace(
  request: APIRequestContext,
  projectId: string,
): Promise<void> {
  for (const file of SHELL_WORKSPACE_FILES) {
    const response = await request.post(`${apiBaseUrl}/files/write`, {
      data: {
        project_id: projectId,
        path: file.path,
        content: file.content,
      },
    })
    await expect(response).toBeOK()
  }
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

async function selectSeededWorkspaceFile(page: Page): Promise<void> {
  const liveDeck = page.getByRole("complementary", {
    name: "Live workspace information",
  })
  const analysisDirectory = liveDeck.getByRole("button", {
    name: "analysis",
    exact: true,
  })
  await expect(analysisDirectory).toBeVisible()
  await analysisDirectory.click()

  const workflowFile = liveDeck.getByRole("button", {
    name: "rnaseq.wdl",
    exact: true,
  })
  await expect(workflowFile).toBeVisible()
  await workflowFile.click()

  const preview = liveDeck.getByTestId("workspace-code-preview")
  await expect(preview).toHaveAttribute("data-language", "wdl")
  await expect(preview).toHaveAttribute("data-highlight-language", "wdl")
  await expect(preview.locator(".shiki")).toBeVisible()
  await expect(preview.locator(".shiki")).toContainText("workflow rnaseq")

  const resultsDirectory = liveDeck.getByRole("button", {
    name: "results",
    exact: true,
  })
  await resultsDirectory.click()
  await expect(
    liveDeck.getByRole("button", { name: "qc-report.json", exact: true }),
  ).toBeVisible()
}

async function resizeDock(page: Page): Promise<void> {
  const dock = page.locator("section[aria-hidden='false']").filter({
    has: page.getByTestId("terminal-dock-tab"),
  })
  const resizeHandle = page.getByRole("separator", {
    name: "Resize terminal",
    exact: true,
  })
  await expect(dock).toHaveCSS("height", "300px")
  await resizeHandle.press("Shift+ArrowUp")
  await expect(dock).toHaveCSS("height", "340px")
}

function usesWorkspaceSheet(page: Page): boolean {
  return (page.viewportSize()?.width ?? 0) <= WORKSPACE_SHEET_MAX
}

function workspaceSurface(page: Page) {
  return usesWorkspaceSheet(page)
    ? page.getByRole("dialog")
    : page.getByTestId("agent-live-deck-rail")
}

async function closeWorkspaceSheetIfOpen(page: Page): Promise<void> {
  if (!usesWorkspaceSheet(page)) return
  const dialog = page.getByRole("dialog")
  if (!(await dialog.isVisible().catch(() => false))) return
  await dialog
    .getByRole("button", { name: "Close workspace panel", exact: true })
    .click()
  await expect(dialog).toHaveCount(0)
}

async function addWorkspaceTab(
  page: Page,
  name: "Files" | "Artifacts" | "DAG" | "Browser",
): Promise<void> {
  await closeWorkspaceSheetIfOpen(page)
  await page.getByTestId("agent-action-add-tab").press("Enter")
  const menu = page.locator('[role="menu"]:visible')
  await expect(menu).toBeVisible()
  await menu.getByRole("menuitem", { name, exact: true }).click()
}

test.describe("Agent workspace shell", () => {
  test("keeps navigation, drawer tabs, terminal, and responsive contracts stable", async ({
    page,
    request,
  }, testInfo) => {
    await disableKeylessAgentProviders(request)
    const project = await createShellProject(request, testInfo)
    await seedShellWorkspace(request, project.id)
    await openAgentShell(page, project.id)

    const viewport = page.viewportSize()
    if (!viewport) throw new Error("Agent shell screenshot requires a viewport")
    const isMobile = viewport.width <= COMPACT_VIEWPORT_MAX
    const usesSheet = usesWorkspaceSheet(page)
    const workspaceActions = page.getByTestId("agent-workspace-action-group")
    const addTabButton = workspaceActions.getByTestId("agent-action-add-tab")
    const workspaceToggle = workspaceActions.locator(
      '[data-workspace-action="panel"]',
    )

    await expect(page.getByTestId("navbar-action-row")).toBeVisible()
    await expect(
      page.getByRole("button", { name: "More preferences", exact: true }),
    ).toBeVisible()
    await expect(addTabButton).toBeVisible()
    await expect(workspaceToggle).toBeVisible()
    await expect(
      workspaceActions.locator("[data-workspace-action]"),
    ).toHaveCount(1)
    expect(
      await workspaceActions
        .locator("[data-workspace-action], [data-testid=agent-action-add-tab]")
        .evaluateAll((actions) =>
          actions.map(
            (action) =>
              action.getAttribute("data-workspace-action") ??
              action.getAttribute("data-testid"),
          ),
        ),
    ).toEqual(["agent-action-add-tab", "panel"])
    for (const testId of [
      "agent-action-files",
      "agent-action-artifacts",
      "agent-action-dag",
      "agent-action-browser",
    ]) {
      await expect(page.getByTestId(testId)).toHaveCount(0)
    }
    await expect(page.getByText(/Subagents/i)).toHaveCount(0)

    await addTabButton.click()
    await expect(page.getByRole("menuitem")).toHaveText([
      "Artifacts",
      "Files",
      "DAG",
      "Browser",
    ])
    await expect(page.getByRole("menuitem", { name: /terminal/i })).toHaveCount(
      0,
    )
    await page.keyboard.press("Escape")
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

    await addWorkspaceTab(page, "Files")
    let surface = workspaceSurface(page)
    await expect(surface).toBeVisible()
    const liveDeck = page.getByRole("complementary", {
      name: "Live workspace information",
    })
    const tabBar = liveDeck.getByTestId("live-deck-tab-bar")
    await expect(tabBar).toBeVisible()
    await expect(tabBar.getByRole("tab")).toHaveText(["Files"])
    await expect(
      tabBar.getByRole("tab", { name: "Files", exact: true }),
    ).toHaveAttribute("aria-selected", "true")

    await selectSeededWorkspaceFile(page)
    await expect(tabBar.getByRole("tab")).toHaveText(["Files", "rnaseq.wdl"])
    await expect(
      tabBar.getByRole("tab", { name: "rnaseq.wdl", exact: true }),
    ).toHaveAttribute("aria-selected", "true")
    await expect(liveDeck.getByTestId("workspace-code-preview")).toContainText(
      "workflow rnaseq",
    )
    await expect(page).toHaveScreenshot(
      `agent-workspace-shell-${viewport.width}x${viewport.height}-populated.png`,
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
    await expect(surface).toHaveScreenshot(
      `agent-workspace-shell-${viewport.width}x${viewport.height}-open.png`,
      { animations: "disabled", caret: "hide" },
    )

    if (usesSheet) {
      await expect(surface).toHaveClass(/overscroll-contain/)
    } else {
      const rail = page.getByTestId("agent-live-deck-rail")
      const workspaceHeader = page.getByTestId("workspace-panel-header")
      const fileTree = page.getByTestId("workspace-file-tree")
      await expect(rail).toHaveAttribute("data-width", "400")
      expect((await workspaceHeader.boundingBox())?.height).toBe(40)
      const railBox = await rail.boundingBox()
      const treeBox = await fileTree.boundingBox()
      expect(railBox).not.toBeNull()
      expect(treeBox).not.toBeNull()
      expect((treeBox?.width ?? 0) / (railBox?.width ?? 1)).toBeGreaterThan(0.3)
      expect((treeBox?.width ?? 0) / (railBox?.width ?? 1)).toBeLessThan(0.35)
    }

    await page.reload()
    surface = workspaceSurface(page)
    await expect(surface).toBeVisible()
    const reloadedLiveDeck = page.getByRole("complementary", {
      name: "Live workspace information",
    })
    const reloadedTabBar = reloadedLiveDeck.getByTestId("live-deck-tab-bar")
    await expect(reloadedTabBar.getByRole("tab")).toHaveText([
      "Files",
      "rnaseq.wdl",
    ])
    await expect(
      reloadedTabBar.getByRole("tab", { name: "rnaseq.wdl", exact: true }),
    ).toHaveAttribute("aria-selected", "true")
    await expect(
      reloadedLiveDeck.getByTestId("workspace-code-preview"),
    ).toContainText("workflow rnaseq")

    await page
      .getByRole("button", { name: "Close workspace panel", exact: true })
      .click()
    await expect(workspaceSurface(page)).toHaveCount(0)
    await expect(workspaceToggle).toHaveAttribute("aria-pressed", "false")
    await workspaceToggle.focus()
    await page.keyboard.press("Enter")
    await expect(workspaceSurface(page)).toBeVisible()
    await expect(workspaceToggle).toHaveAttribute("aria-pressed", "true")
    await page.keyboard.press("Control+Shift+b")
    await expect(workspaceSurface(page)).toHaveCount(0)
    await expect(workspaceToggle).toHaveAttribute("aria-pressed", "false")
    await page.keyboard.press("Control+Shift+b")
    await expect(workspaceSurface(page)).toBeVisible()
    await expect(workspaceToggle).toHaveAttribute("aria-pressed", "true")

    for (const [label, region] of [
      ["Artifacts", liveDeck.getByRole("region", { name: "Agent artifacts" })],
      ["DAG", liveDeck.locator(".react-flow")],
      ["Browser", liveDeck.getByRole("region", { name: "Built-in browser" })],
    ] as const) {
      await addWorkspaceTab(page, label)
      surface = workspaceSurface(page)
      await expect(
        surface.getByRole("tab", { name: label, exact: true }),
      ).toHaveAttribute("aria-selected", "true")
      await expect(region).toBeVisible()
    }
    await expect(liveDeck.getByRole("tab")).toHaveText([
      "Files",
      "rnaseq.wdl",
      "Artifacts",
      "DAG",
      "Browser",
    ])
    await liveDeck.getByRole("tab", { name: "Files", exact: true }).click()
    await expect(
      liveDeck.getByRole("region", { name: "Project file browser" }),
    ).toBeVisible()
    await liveDeck.getByRole("tab", { name: "rnaseq.wdl", exact: true }).click()
    await expect(liveDeck.getByTestId("workspace-code-preview")).toContainText(
      "workflow rnaseq",
    )
    await liveDeck.getByRole("tab", { name: "Browser", exact: true }).click()
    await liveDeck
      .getByRole("tab", { name: "Browser", exact: true })
      .locator("..")
      .getByRole("button", { name: "Close Browser", exact: true })
      .press("Enter")
    await expect(
      liveDeck.getByRole("tab", { name: "Browser", exact: true }),
    ).toHaveCount(0)
    await expect(
      liveDeck.getByRole("tab", { name: "DAG", exact: true }),
    ).toHaveAttribute("aria-selected", "true")

    if (!usesSheet) {
      const rail = page.getByTestId("agent-live-deck-rail")
      const resizeHandle = page.getByRole("separator", {
        name: "Resize workspace panel",
      })
      await expect(rail).toHaveAttribute("data-width", "400")
      for (let index = 0; index < 6; index += 1) {
        await resizeHandle.press("Shift+ArrowLeft")
      }
      await expect(rail).toHaveAttribute("data-width", "600")
      for (let index = 0; index < 10; index += 1) {
        await resizeHandle.press("Shift+ArrowRight")
      }
      await expect(rail).toHaveAttribute("data-width", "300")
      await page.reload()
      await expect(page.getByTestId("agent-live-deck-rail")).toHaveAttribute(
        "data-width",
        "300",
      )
    }

    await closeWorkspaceSheetIfOpen(page)
    if (!usesSheet) {
      await page
        .getByRole("button", { name: "Close workspace panel", exact: true })
        .click()
    }
    await expect(workspaceSurface(page)).toHaveCount(0)
    await page.getByRole("button", { name: "Open terminal", exact: true }).click()
    await expect(page.getByTestId("terminal-dock-tab")).toBeVisible()
    await expect(page.getByTestId("terminal-dock-fixture")).toBeVisible()

    if (isMobile) {
      const terminalSheet = page.locator('[data-slot="sheet-content"]').filter({
        has: page.getByTestId("terminal-dock-tab"),
      })
      await expect(terminalSheet).toBeVisible()
      await expect(terminalSheet).toHaveClass(/inset-x-0/)
      await expect(terminalSheet).toHaveClass(/bottom-0/)
      await expect(terminalSheet).toHaveClass(/h-\[72vh\]/)
      await expect(terminalSheet).toHaveScreenshot(
        `agent-workspace-shell-${viewport.width}x${viewport.height}-open-terminal.png`,
        { animations: "disabled", caret: "hide" },
      )
    } else {
      await resizeDock(page)
      await expect(page).toHaveScreenshot(
        `agent-workspace-shell-${viewport.width}x${viewport.height}-open-terminal.png`,
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
      await page.reload()
      await page
        .getByRole("button", { name: "Open terminal", exact: true })
        .click()
      const reloadedDock = page.locator("section[aria-hidden='false']").filter({
        has: page.getByTestId("terminal-dock-tab"),
      })
      await expect(reloadedDock).toHaveCSS("height", "340px")
    }
    await page.getByRole("button", { name: "Close terminal", exact: true }).click()
    await expect(page.getByTestId("terminal-dock-tab")).toHaveCount(0)
  })

  test("persists multiple closable drawer tabs and selects a neighbor", async ({
    page,
    request,
  }, testInfo) => {
    await disableKeylessAgentProviders(request)
    const project = await createShellProject(request, testInfo)
    await openAgentShell(page, project.id)
    await addWorkspaceTab(page, "Files")
    await addWorkspaceTab(page, "Artifacts")
    await addWorkspaceTab(page, "Browser")
    let surface = workspaceSurface(page)
    const liveDeck = page.getByRole("complementary", {
      name: "Live workspace information",
    })
    await expect(surface.getByRole("tab")).toHaveText([
      "Files",
      "Artifacts",
      "Browser",
    ])

    await liveDeck.getByRole("tab", { name: "Artifacts", exact: true }).click()
    await liveDeck
      .getByRole("tab", { name: "Artifacts", exact: true })
      .locator("..")
      .getByRole("button", { name: "Close Artifacts", exact: true })
      .press("Enter")
    await expect(
      liveDeck.getByRole("tab", { name: "Browser", exact: true }),
    ).toHaveAttribute("aria-selected", "true")
    await page.reload()
    surface = workspaceSurface(page)
    await expect(surface).toBeVisible()
    await expect(surface.getByRole("tab")).toHaveText(["Files", "Browser"])

    await liveDeck
      .getByRole("tab", { name: "Browser", exact: true })
      .locator("..")
      .getByRole("button", { name: "Close Browser", exact: true })
      .press("Enter")
    await expect(
      liveDeck.getByRole("tab", { name: "Files", exact: true }),
    ).toHaveAttribute("aria-selected", "true")
    await liveDeck
      .getByRole("tab", { name: "Files", exact: true })
      .locator("..")
      .getByRole("button", { name: "Close Files", exact: true })
      .press("Enter")
    await expect(workspaceSurface(page)).toHaveCount(0)
    await expect(
      page.getByRole("button", { name: "Open workspace panel", exact: true }),
    ).toHaveAttribute("aria-pressed", "false")
  })

  test("keeps the multi-tab Drawer separate from the bottom Terminal Dock", async ({
    page,
    request,
  }, testInfo) => {
    await disableKeylessAgentProviders(request)
    const project = await createShellProject(request, testInfo)
    await openAgentShell(page, project.id)
    await addWorkspaceTab(page, "Files")
    await addWorkspaceTab(page, "Artifacts")
    await addWorkspaceTab(page, "Browser")
    const viewport = page.viewportSize()
    if (!viewport) throw new Error("Agent shell screenshot requires a viewport")
    const surface = workspaceSurface(page)
    await expect(surface.getByRole("tab")).toHaveText([
      "Files",
      "Artifacts",
      "Browser",
    ])
    await page.evaluate(() => document.fonts.ready)
    await expect(page).toHaveScreenshot(
      `workspace-tabs-${viewport.width}x${viewport.height}.png`,
      { animations: "disabled", caret: "hide" },
    )

    await closeWorkspaceSheetIfOpen(page)
    if (!usesWorkspaceSheet(page)) {
      await page
        .getByRole("button", { name: "Close workspace panel", exact: true })
        .click()
    }
    await page.getByRole("button", { name: "Open terminal", exact: true }).click()
    await expect(page.getByTestId("terminal-dock-tab")).toBeVisible()
    await page.evaluate(() => document.fonts.ready)
    await expect(page).toHaveScreenshot(
      `drawer-terminal-${viewport.width}x${viewport.height}.png`,
      { animations: "disabled", caret: "hide" },
    )
  })
})
