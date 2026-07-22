import { chromium } from "@playwright/test"

const baseURL = process.env.LANDING_REVIEW_BASE_URL || "http://localhost:3104/landing-preview"
const viewports = [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
  { width: 768, height: 900 },
  { width: 414, height: 896 },
  { width: 375, height: 812 },
]

const browser = await chromium.launch({ headless: true })
const failures = []

try {
  for (const locale of ["en", "zh-CN"]) {
    for (const viewport of viewports) {
      const context = await browser.newContext({
        viewport,
        colorScheme: "light",
        reducedMotion: viewport.width < 900 ? "reduce" : "no-preference",
      })
      await context.addCookies([{ name: "NEXT_LOCALE", value: locale, url: baseURL }])
      const page = await context.newPage()
      const consoleErrors = []
      page.on("console", (message) => {
        if (message.type() === "error") consoleErrors.push(message.text())
      })

      await page.goto(baseURL, { waitUntil: "domcontentloaded" })
      await page.waitForTimeout(600)

      const metrics = await page.evaluate(() => ({
        clientWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
        heading: document.querySelector("h1")?.textContent?.replace(/\s+/g, " ").trim(),
        staticStages: document.querySelectorAll(".landing-static-story article").length,
      }))

      if (metrics.scrollWidth > metrics.clientWidth) {
        failures.push(`${locale} ${viewport.width}px overflows by ${metrics.scrollWidth - metrics.clientWidth}px`)
      }
      const expectedHeading = locale === "zh-CN"
        ? "用自然语言分析生物信息学"
        : "Bioinformatics in plain language."
      if (metrics.heading !== expectedHeading) {
        failures.push(`${locale} ${viewport.width}px has the wrong hero heading: ${metrics.heading}`)
      }
      if (viewport.width < 900 && metrics.staticStages !== 4) {
        failures.push(`${locale} ${viewport.width}px does not expose all four static product stages`)
      }
      if (consoleErrors.length) {
        failures.push(`${locale} ${viewport.width}px console errors: ${consoleErrors.join(" | ")}`)
      }

      await context.close()
    }
  }

  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await context.newPage()
  await page.goto(baseURL, { waitUntil: "domcontentloaded" })
  await page.waitForTimeout(600)
  await page.evaluate(() => window.scrollTo({ top: 1050, behavior: "instant" }))
  await page.waitForTimeout(350)
  const productFrame = await page.locator(".landing-product-frame").boundingBox()
  if (!productFrame || productFrame.width < 1200 || productFrame.y > 260) {
    failures.push("desktop product frame did not expand into the pinned product stage")
  }
  await context.close()

  const demoContext = await browser.newContext({ viewport: { width: 1280, height: 800 } })
  const demoPage = await demoContext.newPage()
  const demoOrigin = new URL(baseURL).origin
  await demoContext.addCookies([{ name: "NEXT_LOCALE", value: "en", url: demoOrigin }])
  await demoPage.goto(demoOrigin, { waitUntil: "domcontentloaded" })
  await demoPage.locator('a[href="/auth"]').first().click()
  await demoPage.locator('a[href*="provider=guest"]').click()
  await demoPage.waitForURL(`${demoOrigin}/agent`)

  await demoPage.goBack()
  await demoPage.waitForURL(`${demoOrigin}/`)
  const landingHeading = await demoPage.locator("h1").textContent()
  if (landingHeading?.replace(/\s+/g, " ").trim() !== "Bioinformatics in plain language.") {
    failures.push("browser back did not return an active demo visitor to landing")
  }

  await demoPage.goto(`${demoOrigin}/agent`, { waitUntil: "domcontentloaded" })
  await demoPage.locator('button[aria-label*="User menu"]').click()
  await demoPage.locator('a[href="/api/demo-auth?action=logout&next=%2F"]').click()
  await demoPage.waitForURL(`${demoOrigin}/`)
  const demoCookies = await demoContext.cookies()
  if (demoCookies.some((cookie) => cookie.name === "bioinfoflow_demo_access" && cookie.value)) {
    failures.push("exit demo did not clear the demo access cookie")
  }
  await demoContext.close()
} finally {
  await browser.close()
}

if (failures.length) {
  console.error(failures.join("\n"))
  process.exit(1)
}

console.log("Landing visual verification passed for English and Chinese at 1440, 1280, 768, 414, and 375px.")
