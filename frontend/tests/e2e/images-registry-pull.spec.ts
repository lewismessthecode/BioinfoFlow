import { test } from "@playwright/test"
import { ImagesPage } from "./pages/images-page"

test.describe("Images registry pull journey", () => {
  test("pulls an image from the registry and makes it reusable from Images", async ({ page }, testInfo) => {
    const images = new ImagesPage(page)
    const imageName = `bioinfoflow/e2e-pull-${testInfo.retry}:1.0.0`
    const imageRepository = `bioinfoflow/e2e-pull-${testInfo.retry}`

    await images.goto()
    await images.expectLoaded()

    await images.openRegistryDialog()
    await images.fillRegistryImageName(imageName)
    await images.submitUpload()

    await images.expectImageVisible(imageRepository)
    await images.refresh()
    await images.expectImageReadyForRepull(imageRepository)
  })
})
