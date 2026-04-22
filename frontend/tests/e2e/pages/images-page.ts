import { expect, type Locator, type Page } from "@playwright/test"
import { AppNav } from "./app-nav"

export class ImagesPage {
  private readonly nav: AppNav

  constructor(private readonly page: Page) {
    this.nav = new AppNav(page)
  }

  get heading(): Locator {
    return this.page.getByRole("heading", { name: "Images" })
  }

  get searchInput(): Locator {
    return this.page.getByPlaceholder("Search images...")
  }

  async expectLoaded() {
    await expect(this.heading).toBeVisible()
    await expect(this.searchInput).toBeVisible()
  }
}
