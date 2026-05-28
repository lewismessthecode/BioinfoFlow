import { expect, test } from "@playwright/test"

test.describe("Auth page smoke", () => {
  test("signs in with the bootstrap owner in personal auth mode", async ({ page }) => {
    await page.goto("/auth")

    await expect(
      page.getByRole("heading", { name: "Sign in to continue", level: 1 }),
    ).toBeVisible()

    await page.getByLabel("Email").fill("admin@example.com")
    await page.getByLabel("Password").fill("changeme")
    await page.getByRole("button", { name: "Sign in with email" }).click()

    await page.waitForURL("**/agent")
    await expect(page).toHaveURL(/\/agent$/)
  })
})
