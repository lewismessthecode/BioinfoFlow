import { expect, type Locator, type Page } from "@playwright/test"
import { AppNav } from "./app-nav"

export class AgentPage {
  private readonly nav: AppNav

  constructor(private readonly page: Page) {
    this.nav = new AppNav(page)
  }

  async goto() {
    await this.page.goto("/agent")
  }

  get emptyStateHeading(): Locator {
    return this.page.getByRole("heading", { name: "Start your first analysis" })
  }

  async expectLoaded() {
    await expect(this.emptyStateHeading).toBeVisible()
  }

  async goToRuns() {
    await this.nav.goTo("Runs", "/runs")
  }
}
