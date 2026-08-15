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

  async gotoSession(sessionId: string) {
    await this.page.goto(`/agent/${sessionId}`)
  }

  get emptyStateHeading(): Locator {
    return this.page.getByRole("heading", {
      name: "What would you like to work on?",
    })
  }

  get messageInput(): Locator {
    return this.page.locator('[data-testid="agent-composer"] textarea')
  }

  get sendButton(): Locator {
    return this.page.getByRole("button", { name: "Send message", exact: true })
  }

  get workbench(): Locator {
    return this.page.getByTestId("agent-workbench")
  }

  get transcript(): Locator {
    return this.page.getByRole("region", { name: "Conversation" })
  }

  get activeRun(): Locator {
    return this.page.getByTestId("agent-active-run")
  }

  get activityGroups(): Locator {
    return this.page.getByTestId("agent-activity-group")
  }

  get approvalCard(): Locator {
    return this.page.getByTestId("agent-interaction-card").filter({
      has: this.page.getByRole("heading", { name: "Approval requested" }),
    })
  }

  get askUserCard(): Locator {
    return this.page.getByTestId("agent-interaction-card").filter({
      has: this.page.getByRole("heading", {
        name: "The agent asked for input",
      }),
    })
  }

  get recoveryCard(): Locator {
    return this.page.getByTestId("agent-interaction-card").filter({
      has: this.page.getByRole("heading", { name: "Recovery requested" }),
    })
  }

  get stopButton(): Locator {
    return this.page.getByRole("button", { name: "Stop run", exact: true })
  }

  async expectLoaded() {
    await expect(this.workbench).toBeVisible({ timeout: 30_000 })
    await expect(this.emptyStateHeading).toBeVisible({ timeout: 30_000 })
  }

  async expectComposerReady() {
    await expect(this.workbench).toBeVisible({ timeout: 30_000 })
    await expect(this.messageInput).toBeVisible({ timeout: 30_000 })
    await expect(this.sendButton).toBeVisible({ timeout: 30_000 })
  }

  async sendMessage(message: string) {
    await this.messageInput.fill(message)
    await this.sendButton.click()
  }

  async expectSessionRoute() {
    await expect(this.page).toHaveURL(/\/agent\/[0-9a-f-]{36}$/i, {
      timeout: 20_000,
    })
  }

  async goToRuns() {
    await this.nav.goTo("Runs", "/runs")
  }
}
