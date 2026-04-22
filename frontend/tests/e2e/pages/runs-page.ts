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
    return this.page.getByPlaceholder("Search runs...")
  }

  async expectLoaded() {
    await expect(this.heading).toBeVisible()
    await expect(this.searchInput).toBeVisible()
  }

  async goToWorkflows() {
    await this.nav.goTo("Workflows", "/workflows")
  }
}
