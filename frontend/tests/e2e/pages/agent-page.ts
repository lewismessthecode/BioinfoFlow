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

  get selectProjectHeading(): Locator {
    return this.page.getByRole("heading", { name: "Select a project to start" })
  }

  get messageInput(): Locator {
    return this.page.getByRole("textbox", { name: "Message" })
  }

  get sendButton(): Locator {
    return this.page.getByRole("button", { name: "Send message", exact: true })
  }

  async expectLoaded() {
    await expect(
      this.page.getByRole("heading", {
        name: /Start your first analysis|Select a project to start/,
      }),
    ).toBeVisible()
  }

  async expectComposerReady() {
    await expect(this.messageInput).toBeVisible()
    await expect(this.sendButton).toBeVisible()
  }

  async sendMessage(message: string) {
    await this.messageInput.fill(message)
    await this.sendButton.click()
  }

  async goToRuns() {
    await this.nav.goTo("Runs", "/runs")
  }
}
