import path from "node:path"
import { test } from "@playwright/test"
import { ImagesPage } from "./pages/images-page"

const tarballFixturePath = path.resolve(process.cwd(), "tests/e2e/fixtures/test-image.tar")

test.describe("Images tarball import journey", () => {
  test("imports a tarball and makes the image reusable from Images", async ({ page }) => {
    const images = new ImagesPage(page)
    const imageRepository = "bioinfoflow/tarball-import-e2e"

    await images.goto()
    await images.expectLoaded()

    await images.openTarballDialog()
    await images.attachTarball(tarballFixturePath)
    await images.submitUpload()

    await images.expectImageVisible(imageRepository)
    await images.refresh()
    await images.expectImageReadyForRepull(imageRepository)
  })
})
