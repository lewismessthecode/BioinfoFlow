import { expect, type Locator, type Page } from "@playwright/test"
import { AppNav } from "./app-nav"

export class RunsPage {
  private readonly nav: AppNav

  constructor(private readonly page: Page) {
    this.nav = new AppNav(page)
  }

  get heading(): Locator {
    return this.page.getByRole("heading", { name: "Runs" })
  }

  get searchInput(): Locator {
    return this.page.getByRole("textbox", { name: "Search Runs" })
  }

  get runRows(): Locator {
    return this.page.locator('tbody > tr[role="button"]')
  }

  row(runId: string): Locator {
    return this.runRows.filter({
      hasText: runId,
    })
  }

  async goto(projectId?: string) {
    const params = new URLSearchParams()
    if (projectId) {
      params.set("project_id", projectId)
      params.set("scope", "project")
    }

    const query = params.toString()
    await this.page.goto(query ? `/runs?${query}` : "/runs")
  }

  async expectLoaded() {
    await expect(this.heading).toBeVisible()
    await expect(this.searchInput).toBeVisible()
  }

  async expectRunCount(count: number) {
    await expect(this.runRows).toHaveCount(count)
  }

  async expectRunVisible(runId: string) {
    await expect(this.row(runId)).toBeVisible()
  }

  async expectRunStatus(runId: string, statusLabel: string) {
    await expect(this.row(runId)).toContainText(statusLabel)
  }

  async resumeRun(runId: string) {
    await this.row(runId).getByRole("button", { name: "Resume from checkpoint" }).click()
  }

  async cancelRun(runId: string) {
    await this.row(runId).getByRole("button", { name: "Cancel Run" }).click()
  }

  async confirmCancel() {
    const dialog = this.page.getByTestId("cancel-confirm-dialog")
    await expect(dialog).toBeVisible()
    await dialog.getByRole("button", { name: "Confirm" }).click()
  }

  async goToWorkflows() {
    await this.nav.goTo("Workflows", "/workflows")
  }
}
