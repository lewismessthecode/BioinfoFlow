import { expect, type Locator, type Page } from "@playwright/test"

export type NavLabel = "Agent" | "Runs" | "Workflows" | "Images"

export class AppNav {
  constructor(private readonly page: Page) {}

  link(label: NavLabel): Locator {
    return this.page.getByRole("link", { name: label, exact: true })
  }

  async goTo(label: NavLabel, path: string) {
    await this.link(label).click()
    await expect(this.page).toHaveURL(new RegExp(`${path}$`))
  }
}
