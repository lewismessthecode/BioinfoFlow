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
    return this.page.getByRole("group", { name: providerLabel, exact: true })
  }

  field(providerLabel: string, fieldLabel: string): Locator {
    return this.page.getByLabel(
      new RegExp(`^${escapeRegExp(providerLabel)} ${escapeRegExp(fieldLabel)}$`, "i"),
    )
  }

  async saveField(providerLabel: string, fieldLabel: string, value: string) {
    const input = this.field(providerLabel, fieldLabel)
    await input.focus()
    await input.fill(value)
    await input.blur()
  }

  protocolSelector(providerLabel: string): Locator {
    return this.providerCard(providerLabel).getByRole("combobox", {
      name: `${providerLabel} protocol`,
    })
  }

  testModelSelector(providerLabel: string): Locator {
    return this.providerCard(providerLabel).getByRole("combobox", {
      name: `${providerLabel} test model`,
    })
  }

  async chooseProtocol(providerLabel: string, protocolLabel: string) {
    await this.protocolSelector(providerLabel).selectOption({ label: protocolLabel })
  }

  async chooseTestModel(providerLabel: string, modelLabel: string) {
    await this.testModelSelector(providerLabel).selectOption({ label: modelLabel })
  }

  saveButton(providerLabel: string): Locator {
    return this.providerCard(providerLabel).getByRole("button", {
      name: "Save",
      exact: true,
    })
  }

  discoverButton(): Locator {
    return this.page.getByRole("button", {
      name: "Refresh models",
      exact: true,
    })
  }

  testButton(providerLabel: string): Locator {
    return this.providerCard(providerLabel).getByRole("button", {
      name: "Test",
      exact: true,
    })
  }

  async clickTest(providerLabel: string) {
    await this.testButton(providerLabel).click()
  }

  async clickSave(providerLabel: string) {
    await this.saveButton(providerLabel).click()
  }

  allowInsecureSwitch(providerLabel: string): Locator {
    return this.providerCard(providerLabel).getByRole("switch", {
      name: "Allow insecure HTTP",
    })
  }

  async allowInsecureHttp(providerLabel: string) {
    const toggle = this.allowInsecureSwitch(providerLabel)
    if ((await toggle.getAttribute("data-state")) !== "checked") {
      await toggle.click()
    }
  }

  async expectProtocol(providerLabel: string, protocolLabel: string) {
    await expect(this.protocolSelector(providerLabel)).toContainText(protocolLabel)
  }

  async expectWriteOnlyKey(providerLabel: string) {
    await expect(this.field(providerLabel, "API key")).toHaveValue("")
    await expect(this.field(providerLabel, "API key")).toHaveAttribute(
      "placeholder",
      /saved|replace/i,
    )
  }

  async expectTestStatus(providerLabel: string, status: RegExp) {
    await expect(this.providerCard(providerLabel)).toContainText(status)
  }

  async expectSuccessState(providerLabel: string) {
    await expect(this.providerCard(providerLabel).getByText("Ready", { exact: true })).toBeVisible()
  }

  async expectFailureState(providerLabel: string) {
    await expect(this.providerCard(providerLabel).getByText("Needs setup", { exact: true })).toBeVisible()
  }
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}
