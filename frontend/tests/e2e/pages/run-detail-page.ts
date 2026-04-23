import { expect, type Page } from "@playwright/test"

export class RunDetailPage {
  constructor(private readonly page: Page) {}

  private outputPanel() {
    return this.page.getByRole("tabpanel", { name: "Output Files", exact: true })
  }

  async expectLoaded(runId: string) {
    await expect(this.page).toHaveURL(new RegExp(`/runs/${runId}$`))
    await expect(this.page.getByRole("heading", { name: runId, exact: true })).toBeVisible()
  }

  async expectDagVisible() {
    await expect(this.page.getByRole("tab", { name: "Pipeline DAG", exact: true })).toBeVisible()
    await expect(this.page.getByRole("button", { name: "Fullscreen", exact: true })).toBeVisible()
  }

  async expectDagNode(label: string) {
    await expect(this.page.getByText(label, { exact: true }).first()).toBeVisible()
  }

  async expectLogsContain(text: string) {
    await this.page.getByRole("tab", { name: "Logs", exact: true }).click()
    await expect(this.page.getByText(text)).toBeVisible()
  }

  async expectAnyLogs() {
    await this.page.getByRole("tab", { name: "Logs", exact: true }).click()
    await expect(this.page.getByText("No logs available")).not.toBeVisible()
    await expect(this.page.locator('[role="tabpanel"][data-state="active"] .font-mono')).toContainText(/\S+/)
  }

  private directoryButton(name: string) {
    return this.outputPanel().getByText(name, { exact: true }).locator("xpath=ancestor::button[1]")
  }

  private fileButton(name: string) {
    return this.outputPanel().getByRole("button").filter({ hasText: name }).first()
  }

  async expectOutputFile(pathSegments: string[]) {
    await this.page.getByRole("tab", { name: "Output Files", exact: true }).click()
    await expect(this.outputPanel().getByRole("button", { name: "Expand", exact: true })).toBeVisible()

    for (const segment of pathSegments.slice(0, -1)) {
      await this.directoryButton(segment).click()
    }

    await expect(this.fileButton(pathSegments.at(-1) ?? "")).toBeVisible()
  }

  async openOutputFile(pathSegments: string[]) {
    await this.expectOutputFile(pathSegments)
    await this.fileButton(pathSegments.at(-1) ?? "").click()
  }

  async expectOutputPreview(text: string) {
    await expect(this.page.getByText(text)).toBeVisible()
  }
}
