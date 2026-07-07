import { expect, test } from "@playwright/test"
import { ImagesPage } from "./pages/images-page"

test.describe("Sidebar layout", () => {
  test("keeps the desktop sidebar pinned during document-level scroll", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })

    const images = new ImagesPage(page)
    await images.goto()
    await images.expectLoaded()

    const sidebar = page.getByRole("complementary", { name: "Project navigation" })
    await expect(sidebar).toBeVisible()

    const before = await sidebar.boundingBox()
    expect(before).not.toBeNull()
    expect(Math.abs(before!.y)).toBeLessThanOrEqual(1)
    expect(before!.height).toBeGreaterThan(850)

    await page.evaluate(() => {
      const spacer = document.createElement("div")
      spacer.dataset.testid = "document-scroll-spacer"
      spacer.style.height = "1600px"
      document.body.appendChild(spacer)
    })

    await page.evaluate(() => window.scrollTo(0, 700))
    await page.waitForFunction(() => window.scrollY > 600)

    const after = await sidebar.boundingBox()
    expect(after).not.toBeNull()
    expect(Math.abs(after!.y)).toBeLessThanOrEqual(1)
    expect(after!.height).toBeGreaterThan(850)
  })
})
