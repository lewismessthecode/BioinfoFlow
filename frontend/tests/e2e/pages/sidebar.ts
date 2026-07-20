import { expect, type Locator, type Page } from "@playwright/test"

export class Sidebar {
  readonly root: Locator

  constructor(private readonly page: Page) {
    this.root = page.getByRole("complementary", { name: "Project navigation" })
  }

  async expectLoaded() {
    await expect(this.root).toBeVisible()
    await expect(
      this.root.getByRole("button", { name: "New Conversation" }).first(),
    ).toBeVisible()
  }

  async openCreateProjectDialog() {
    await this.root.getByRole("button", { name: "New Project" }).click()
    await expect(this.page.getByRole("dialog")).toBeVisible()
  }

  async createProject(name: string, description = "") {
    await this.openCreateProjectDialog()
    await this.page.getByLabel("Project Name").fill(name)
    if (description) {
      await this.page.getByLabel("Project Description").fill(description)
    }
    await this.page.getByRole("button", { name: "Create Project", exact: true }).click()
    await expect(this.page.getByRole("dialog")).not.toBeVisible()
  }

  projectButton(name: string): Locator {
    return this.root.getByRole("button", { name, exact: true })
  }

  async selectProject(name: string) {
    await this.projectButton(name).click()
  }
}
