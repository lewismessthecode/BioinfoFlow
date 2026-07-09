import { expect, type Locator, type Page } from "@playwright/test"

export class SettingsPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto("/settings")
  }

  get heading(): Locator {
    return this.page.getByText("Settings", { exact: true }).first()
  }

  async expectLoaded() {
    await expect(this.heading).toBeVisible()
  }

  async openProvidersSection() {
    await this.page.getByRole("link", { name: "AI Providers", exact: true }).click()
    await expect(
      this.page.getByText("Configure your API keys and select which model powers the agent."),
    ).toBeVisible()
  }

  providerCard(providerLabel: string): Locator {
    return this.page
      .getByText(providerLabel, { exact: true })
      .locator('xpath=ancestor::*[@data-slot="card"][1]')
  }

  field(providerLabel: string, fieldLabel: string): Locator {
    return this.page.getByLabel(`${providerLabel} ${fieldLabel}`, { exact: true })
  }

  async saveField(providerLabel: string, fieldLabel: string, value: string) {
    const input = this.field(providerLabel, fieldLabel)
    await input.focus()
    await input.fill(value)
    await input.blur()
  }

  testButton(providerLabel: string): Locator {
    return this.providerCard(providerLabel).getByRole("button").last()
  }

  async clickTest(providerLabel: string) {
    await this.testButton(providerLabel).click()
  }

  async expectSuccessState(providerLabel: string) {
    await expect(this.providerCard(providerLabel).getByText("Ready", { exact: true })).toBeVisible()
  }

  async expectFailureState(providerLabel: string) {
    await expect(this.providerCard(providerLabel).getByText("Needs setup", { exact: true })).toBeVisible()
  }
}
