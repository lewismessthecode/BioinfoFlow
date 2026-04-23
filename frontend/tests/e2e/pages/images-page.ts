import { expect, type Locator, type Page } from "@playwright/test"
import { AppNav } from "./app-nav"

export class ImagesPage {
  private readonly nav: AppNav

  constructor(private readonly page: Page) {
    this.nav = new AppNav(page)
  }

  async goto() {
    await this.page.goto("/images")
  }

  get heading(): Locator {
    return this.page.getByRole("heading", { name: "Images", exact: true })
  }

  get searchInput(): Locator {
    return this.page.getByRole("textbox", { name: "Search Images" })
  }

  get uploadButton(): Locator {
    return this.page.getByRole("button", { name: "Upload Image", exact: true })
  }

  get emptyStatePullButton(): Locator {
    return this.page.getByRole("button", { name: "Pull from registry", exact: true })
  }

  get emptyStateTarballButton(): Locator {
    return this.page.getByRole("button", { name: "Import tarball", exact: true })
  }

  get refreshButton(): Locator {
    return this.page.getByRole("button", { name: "Refresh", exact: true })
  }

  get uploadDialog(): Locator {
    return this.page.getByRole("dialog", { name: "Upload Docker Image" })
  }

  imageTitle(name: string): Locator {
    return this.page.locator("h2").filter({ hasText: name })
  }

  private imageCard(name: string): Locator {
    return this.page
      .getByRole("heading", { name, exact: true })
      .locator("xpath=ancestor::div[contains(@class, 'group')][1]")
  }

  async expectLoaded() {
    await expect(this.heading).toBeVisible()
    await expect(this.searchInput).toBeVisible()
  }

  async openRegistryDialog() {
    if (await this.emptyStatePullButton.isVisible()) {
      await this.emptyStatePullButton.click()
    } else {
      await this.uploadButton.click()
    }
    await expect(this.uploadDialog).toBeVisible()
  }

  async fillRegistryImageName(value: string) {
    await this.uploadDialog.getByLabel("Image Name").fill(value)
  }

  async openTarballDialog() {
    if (await this.emptyStateTarballButton.isVisible()) {
      await this.emptyStateTarballButton.click()
    } else {
      await this.uploadButton.click()
      await this.uploadDialog.getByRole("button", { name: "From Tarball", exact: true }).click()
    }
    await expect(this.uploadDialog).toBeVisible()
  }

  async attachTarball(filePath: string) {
    await this.uploadDialog.getByLabel("Tarball (.tar)").setInputFiles(filePath)
  }

  async submitUpload() {
    await this.uploadDialog.getByRole("button", { name: "Pull Image", exact: true }).click()
  }

  async refresh() {
    await this.refreshButton.click()
  }

  async expectImageVisible(name: string) {
    await expect(this.imageTitle(name)).toBeVisible({ timeout: 30_000 })
  }

  async expectImageReadyForRepull(name: string) {
    await expect(this.imageCard(name).getByRole("button", { name: "Re-pull", exact: true })).toBeVisible({
      timeout: 30_000,
    })
  }
}
