import { expect, type Locator, type Page } from "@playwright/test"
import { AppNav } from "./app-nav"

export class WorkflowsPage {
  private readonly nav: AppNav

  constructor(private readonly page: Page) {
    this.nav = new AppNav(page)
  }

  get heading(): Locator {
    return this.page.getByRole("heading", { name: "Workflows", exact: true })
  }

  get searchInput(): Locator {
    return this.page.getByRole("textbox", { name: "Search Workflows" })
  }

  async expectLoaded() {
    await expect(this.heading).toBeVisible()
    await expect(this.searchInput).toBeVisible()
  }

  async goToImages() {
    await this.nav.goTo("Images", "/images")
  }
}
