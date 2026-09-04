import { expect, test, type APIRequestContext, type Page, type TestInfo } from "@playwright/test"

import { COMPACT_VIEWPORT_MAX } from "../../lib/layout-breakpoints"
import { disableKeylessAgentProviders } from "./support/keyless-agent"

const backendPort = Number(process.env.PLAYWRIGHT_BACKEND_PORT || 8100)
const apiBaseUrl = `http://127.0.0.1:${backendPort}/api/v1`

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
  await expect(preview).toHaveAttribute("data-highlight-language", "scala")
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

test.describe("Agent workspace shell", () => {
  test("keeps navigation, panel, terminal, and responsive contracts stable", async ({
    page,
    request,
  }, testInfo) => {
    await disableKeylessAgentProviders(request)
    const project = await createShellProject(request, testInfo)
    await seedShellWorkspace(request, project.id)
    await openAgentShell(page, project.id)

    await expect(page.getByTestId("navbar-action-row")).toBeVisible()
    await expect(
      page.getByRole("button", { name: "More preferences", exact: true }),
    ).toBeVisible()
    await expect(
      page.getByRole("button", { name: "Open browser", exact: true }),
    ).toBeVisible()
    await expect(
      page.getByRole("button", { name: "Open files", exact: true }),
    ).toBeVisible()
    await expect(
      page.getByRole("button", { name: "Open artifacts", exact: true }),
    ).toBeVisible()
    await expect(
      page.getByRole("button", { name: "Open DAG", exact: true }),
    ).toBeVisible()
    await expect(page.getByText(/Subagents/i)).toHaveCount(0)
    const viewport = page.viewportSize()
    if (!viewport) throw new Error("Agent shell screenshot requires a viewport")
    await expect(page).toHaveScreenshot(
      `agent-workspace-shell-${viewport.width}x${viewport.height}.png`,
      {
        animations: "disabled",
        caret: "hide",
        maxDiffPixels: 0,
        maxDiffPixelRatio: 0,
        mask: [
          page.locator("#sidebar-workspace-tree"),
          page.getByText(project.name, { exact: true }),
        ],
        maskColor: "#ff00ff",
      },
    )

    const isCompact = (page.viewportSize()?.width ?? 0) <= COMPACT_VIEWPORT_MAX
    const filesButton = page.getByTestId("agent-action-files")
    await page.emulateMedia({ colorScheme: "dark" })
    await filesButton.click()
    await expect(
      isCompact
        ? page.getByRole("dialog")
        : page.getByTestId("agent-live-deck-rail"),
    ).toBeVisible()
    const openSurface = isCompact
      ? page.getByRole("dialog")
      : page.getByTestId("agent-live-deck-rail")
    await selectSeededWorkspaceFile(page)
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
    await expect(openSurface).toHaveScreenshot(
      `agent-workspace-shell-${viewport.width}x${viewport.height}-open.png`,
      {
        animations: "disabled",
        caret: "hide",
      },
    )
    if (!isCompact) {
      await page.getByRole("button", { name: "Open terminal", exact: true }).click()
      await expect(page.getByTestId("terminal-dock-fixture")).toBeVisible()
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
    }
    if (isCompact) {
      await page.keyboard.press("Escape")
    } else {
      await filesButton.click()
    }
    await expect(page.getByTestId("agent-live-deck-rail")).toHaveCount(0)
    await expect(page.getByRole("dialog")).toHaveCount(0)
    if (isCompact) {
      await page.getByRole("button", { name: "Open terminal", exact: true }).click()
      await expect(page.getByTestId("terminal-dock-fixture")).toBeVisible()
      const terminalSheet = page.locator('[data-slot="sheet-content"]').filter({
        has: page.getByTestId("terminal-dock-tab"),
      })
      await expect(terminalSheet).toBeVisible()
      await expect(terminalSheet).toHaveClass(/inset-x-0/)
      await expect(terminalSheet).toHaveClass(/bottom-0/)
      await expect(terminalSheet).toHaveClass(/h-\[72vh\]/)
      await expect(terminalSheet).toHaveScreenshot(
        `agent-workspace-shell-${viewport.width}x${viewport.height}-open-terminal.png`,
        {
          animations: "disabled",
          caret: "hide",
        },
      )
      await page.getByRole("button", { name: "Close terminal", exact: true }).click()
      await expect(page.getByTestId("terminal-dock-tab")).toHaveCount(0)
    }
    const filesBox = await filesButton.boundingBox()
    expect(filesBox).not.toBeNull()
    if (isCompact) {
      expect(filesBox?.width).toBeGreaterThanOrEqual(28)
      expect(filesBox?.height).toBeGreaterThanOrEqual(28)
    } else {
      expect(filesBox?.width).toBeGreaterThan(36)
      expect(filesBox?.width).toBeLessThanOrEqual(120)
      expect(filesBox?.height).toBeLessThanOrEqual(36)
    }
    await filesButton.focus()
    await expect(filesButton).toBeFocused()
    await page.keyboard.press("Enter")

    const liveDeck = page.getByRole("complementary", {
      name: "Live workspace information",
    })
    if (isCompact) {
      await expect(page.getByRole("dialog")).toBeVisible()
      await expect(page.getByTestId("agent-live-deck-rail")).toHaveCount(0)
    } else {
      await expect(page.getByTestId("agent-live-deck-rail")).toBeVisible()
    }
    await expect(liveDeck).toBeVisible()
    for (const tabName of ["Files", "Workflow", "Artifacts", "Browser"]) {
      await expect(liveDeck.getByRole("tab", { name: tabName })).toBeVisible()
    }
    await expect(liveDeck.getByRole("tab", { name: "Files" })).toHaveAttribute(
      "data-state",
      "active",
    )
    await expect(filesButton).toHaveAttribute("aria-pressed", "true")

    for (const [actionId, tabName] of [
      ["browser", "Browser"],
      ["artifacts", "Artifacts"],
      ["dag", "Workflow"],
      ["files", "Files"],
    ] as const) {
      if (isCompact) {
        await page.keyboard.press("Escape")
        await expect(page.getByRole("dialog")).toHaveCount(0)
      }
      const action = page.getByTestId(`agent-action-${actionId}`)
      await action.click()
      await expect(action).toHaveAttribute("aria-pressed", "true")
      await expect(liveDeck.getByRole("tab", { name: tabName })).toHaveAttribute(
        "data-state",
        "active",
      )
      for (const otherActionId of ["browser", "files", "artifacts", "dag"]) {
        if (otherActionId === actionId) continue
        await expect(page.getByTestId(`agent-action-${otherActionId}`)).toHaveAttribute(
          "aria-pressed",
          "false",
        )
      }
    }

    if (isCompact) {
      await page.keyboard.press("Escape")
      await expect(liveDeck).toHaveCount(0)
      await expect(filesButton).toHaveAttribute("aria-pressed", "false")
      await expect(filesButton).toBeFocused()
    } else {
      await filesButton.click()
      await expect(liveDeck).toHaveCount(0)
      await expect(filesButton).toHaveAttribute("aria-pressed", "false")
      await filesButton.click()
      await expect(liveDeck).toBeVisible()
      await page
        .getByTestId("live-deck-tab-bar")
        .getByRole("button", { name: "Hide panel", exact: true })
        .click()
      await expect(liveDeck).toHaveCount(0)
      await expect(filesButton).toBeFocused()
      await filesButton.click()
      await expect(liveDeck).toBeVisible()
      await liveDeck.getByRole("tab", { name: "Files" }).focus()
      await page.keyboard.press("Escape")
      await expect(liveDeck).toHaveCount(0)
      await expect(filesButton).toBeFocused()
    }

    if (isCompact) {
      await expect(page.getByTestId("agent-live-deck-rail")).toHaveCount(0)
      await filesButton.click()
      await expect(page.getByRole("dialog")).toBeVisible()
      await page.keyboard.press("Escape")
      await expect(page.getByRole("dialog")).toHaveCount(0)
      await expect(filesButton).toBeFocused()
      await page.keyboard.press("Control+Shift+b")
      await expect(page.getByRole("dialog")).toBeVisible()
      await expect(filesButton).toHaveAttribute("aria-pressed", "true")
      await liveDeck.getByRole("tab", { name: "Files" }).focus()
      await page.keyboard.press("Control+Shift+b")
      await expect(page.getByRole("dialog")).toHaveCount(0)
      await expect(filesButton).toBeFocused()

      await filesButton.click()
      const compactPanel = page.getByRole("dialog")
      await expect(compactPanel).toBeVisible()
      await compactPanel.getByRole("tab", { name: "Artifacts" }).click()
      await expect(
        compactPanel.getByRole("tab", { name: "Artifacts" }),
      ).toHaveAttribute("data-state", "active")
      await page.reload()
      const reloadedCompactPanel = page.getByRole("dialog")
      await expect(reloadedCompactPanel).toBeVisible()
      await expect(
        reloadedCompactPanel.getByRole("tab", { name: "Artifacts" }),
      ).toHaveAttribute("data-state", "active")
      await expect(page.getByTestId("agent-action-artifacts")).toHaveAttribute(
        "aria-pressed",
        "true",
      )
      await page.keyboard.press("Escape")
      await expect(page.getByRole("dialog")).toHaveCount(0)
    } else {
      await filesButton.click()
      const rail = page.getByTestId("agent-live-deck-rail")
      const resizeHandle = page.getByRole("separator", {
        name: "Resize workspace panel",
      })
      await expect(rail).toHaveAttribute("data-width", "400")
      await expect(resizeHandle).toHaveAttribute("aria-valuenow", "400")
      await expect(resizeHandle).toHaveClass(/focus-visible:ring-2/)
      const handleBox = await resizeHandle.boundingBox()
      expect(handleBox).not.toBeNull()
      await page.mouse.move(
        (handleBox?.x ?? 0) + (handleBox?.width ?? 0) / 2,
        (handleBox?.y ?? 0) + 12,
      )
      await page.mouse.down()
      await page.mouse.move(
        (handleBox?.x ?? 0) - 40,
        (handleBox?.y ?? 0) + 12,
      )
      await expect
        .poll(async () => Number(await rail.getAttribute("data-width")))
        .toBeGreaterThan(400)
      await page.mouse.up()
      await expect
        .poll(async () => Number(await rail.getAttribute("data-width")))
        .toBeGreaterThan(400)
      for (let index = 0; index < 6; index += 1) {
        await resizeHandle.press("Shift+ArrowLeft")
      }
      await expect(rail).toHaveAttribute("data-width", "600")
      await expect(resizeHandle).toHaveAttribute("aria-valuenow", "600")
      for (let index = 0; index < 10; index += 1) {
        await resizeHandle.press("Shift+ArrowRight")
      }
      await expect(rail).toHaveAttribute("data-width", "300")
      await expect(resizeHandle).toHaveAttribute("aria-valuenow", "300")
      await page.reload()
      await expect(page.getByTestId("agent-live-deck-rail")).toHaveAttribute(
        "data-width",
        "300",
      )
      await expect(
        page.getByRole("separator", { name: "Resize workspace panel" }),
      ).toHaveAttribute("aria-valuenow", "300")
      await expect(liveDeck.getByRole("tab", { name: "Files" })).toHaveAttribute(
        "data-state",
        "active",
      )
      await expect(filesButton).toHaveAttribute("aria-pressed", "true")
      await liveDeck.getByRole("tab", { name: "Files" }).focus()
      await page.keyboard.press("Control+Shift+b")
      await expect(page.getByTestId("agent-live-deck-rail")).toHaveCount(0)
      await expect(filesButton).toBeFocused()
    }

    if (isCompact || (await page.getByTestId("terminal-dock-tab").count()) === 0) {
      await page.getByRole("button", { name: "Open terminal", exact: true }).click()
    }
    await expect(page.getByTestId("terminal-dock-tab")).toBeVisible()
    await expect(page.getByTestId("terminal-dock-fixture")).toBeVisible()
    if (!isCompact) {
      await resizeDock(page)
      await page.reload()
      await expect(page.getByTestId("terminal-dock-tab")).toHaveCount(0)
      await page.getByRole("button", { name: "Open terminal", exact: true }).click()
      await expect(page.getByTestId("terminal-dock-tab")).toBeVisible()
      const reloadedDock = page.locator("section[aria-hidden='false']").filter({
        has: page.getByTestId("terminal-dock-tab"),
      })
      await expect(reloadedDock).toHaveCSS("height", "340px")
    }
    await page.getByRole("button", { name: "Close terminal", exact: true }).click()
    await expect(page.getByTestId("terminal-dock-tab")).toHaveCount(0)

    if (isCompact) {
      await filesButton.click()
      await expect(liveDeck).toBeVisible()
      await page.getByRole("button", { name: "Hide panel", exact: true }).click()
      await expect(liveDeck).toHaveCount(0)
    }
  })
})
