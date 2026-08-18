import { chromium } from "@playwright/test"

const baseURL = process.env.LANDING_REVIEW_BASE_URL || "http://localhost:3104/landing-preview"
const viewports = [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
  { width: 1024, height: 900 },
  { width: 768, height: 900 },
  { width: 414, height: 896 },
  { width: 375, height: 812 },
]
const locales = ["en", "zh-CN"]
const themes = ["light", "dark"]

const browser = await chromium.launch({ headless: true })
const failures = []

async function openDemoUserMenu(page) {
  const trigger = page.locator('button[aria-label*="User menu"]')
  const exitDemo = page.locator('a[href="/api/demo-auth?action=logout&next=%2F"]')

  for (let attempt = 0; attempt < 30; attempt += 1) {
    await trigger.click()
    await page.waitForTimeout(250)
    if (await exitDemo.isVisible()) return exitDemo
  }

  throw new Error("Demo user menu did not become interactive")
}

try {
  for (const theme of themes) {
    for (const locale of locales) {
      for (const viewport of viewports) {
        const context = await browser.newContext({
          viewport,
          colorScheme: theme,
          reducedMotion: viewport.width < 900 ? "reduce" : "no-preference",
        })
        await context.addCookies([{ name: "NEXT_LOCALE", value: locale, url: baseURL }])
        const page = await context.newPage()
        const consoleErrors = []
        page.on("console", (message) => {
          if (message.type() === "error") consoleErrors.push(message.text())
        })
        await page.addInitScript((selectedTheme) => {
          localStorage.setItem("theme", selectedTheme)
          document.documentElement.classList.toggle("dark", selectedTheme === "dark")
          document.documentElement.style.colorScheme = selectedTheme
        }, theme)

        await page.goto(baseURL, { waitUntil: "domcontentloaded" })
        await page.waitForTimeout(600)

        const metrics = await page.evaluate(() => ({
          clientWidth: document.documentElement.clientWidth,
          scrollWidth: document.documentElement.scrollWidth,
          heading: document.querySelector("h1")?.textContent?.replace(/\s+/g, " ").trim(),
          description: document.querySelector(".landing-hero-copy p")?.textContent?.replace(/\s+/g, " ").trim(),
          staticStages: document.querySelectorAll(".landing-static-story article").length,
          usesDarkTheme: document.documentElement.classList.contains("dark"),
        }))

        const label = `${theme} ${locale} ${viewport.width}px`
        if (metrics.scrollWidth > metrics.clientWidth) {
          failures.push(`${label} overflows by ${metrics.scrollWidth - metrics.clientWidth}px`)
        }
        const expectedHeading = locale === "zh-CN"
          ? "用自然语言分析生物信息学"
          : "Bioinformatics in plain language."
        if (metrics.heading !== expectedHeading) {
          failures.push(`${label} has wrong hero heading: ${metrics.heading}`)
        }
        const expectedDescription = locale === "zh-CN"
          ? "说出你的分析目标，剩下的交给 Agent。"
          : "Describe the analysis goal. The Agent handles the rest."
        if (metrics.description !== expectedDescription) {
          failures.push(`${label} has wrong hero subtitle: ${metrics.description}`)
        }
        if (metrics.usesDarkTheme !== (theme === "dark")) {
          failures.push(`${label} did not apply requested theme`)
        }
        if (viewport.width < 900 && metrics.staticStages !== 4) {
          failures.push(`${label} does not expose all four static product stages`)
        }
        if (viewport.width < 1024) {
          const menuButton = page.locator('button[aria-controls="landing-navigation-menu"]')
          if (!(await menuButton.isVisible())) {
            failures.push(`${label} does not expose compact navigation`)
          } else {
            await menuButton.focus()
            await page.keyboard.press("Enter")
            if (await menuButton.getAttribute("aria-expanded") !== "true") {
              failures.push(`${label} does not open compact navigation by keyboard`)
            }
            if (!(await page.locator("#landing-navigation-menu").isVisible())) {
              failures.push(`${label} does not expose compact navigation content`)
            }
            await page.keyboard.press("Escape")
            await page.waitForTimeout(350)
            if (await menuButton.getAttribute("aria-expanded") !== "false") {
              failures.push(`${label} does not close compact navigation with Escape`)
            }
            const returnedFocus = await page.evaluate(() =>
              document.activeElement?.getAttribute("aria-controls") === "landing-navigation-menu"
            )
            if (!returnedFocus) {
              failures.push(`${label} does not return focus after closing compact navigation`)
            }
          }
        }
        if (consoleErrors.length) {
          failures.push(`${label} console errors: ${consoleErrors.join(" | ")}`)
        }

        await context.close()
      }
    }
  }

  const storyContext = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  await storyContext.addCookies([{ name: "NEXT_LOCALE", value: "en", url: baseURL }])
  const storyPage = await storyContext.newPage()
  await storyPage.goto(baseURL, { waitUntil: "domcontentloaded" })
  await storyPage.waitForTimeout(600)
  await storyPage.evaluate(() => window.scrollTo({ top: 1050, behavior: "instant" }))
  await storyPage.waitForTimeout(350)
  const productFrame = await storyPage.locator(".landing-product-frame").boundingBox()
  if (!productFrame || productFrame.width < 1200 || productFrame.y > 260) {
    failures.push("desktop product frame did not expand into pinned product stage")
  }

  const localeConsoleErrors = []
  storyPage.on("console", (message) => {
    if (message.type() === "error") localeConsoleErrors.push(message.text())
  })
  const header = storyPage.locator("header.landing-navigation")
  if (await header.getAttribute("data-scrolled") !== "true") {
    failures.push("desktop header did not sample restored scroll state")
  }
  await storyPage.getByRole("button", { name: "Select language" }).click()
  await storyPage.getByRole("menuitem", { name: "简体中文" }).click()
  await storyPage.waitForFunction(
    () => document.querySelector("h1")?.textContent?.trim() === "用自然语言分析生物信息学"
  )
  await storyPage.waitForTimeout(350)

  const headerBox = await header.boundingBox()
  const refreshedFrame = await storyPage.locator(".landing-product-frame").boundingBox()
  const localeMetrics = await storyPage.evaluate(() => ({
    scrollY: window.scrollY,
    scrolled: document.querySelector("header.landing-navigation")?.getAttribute("data-scrolled"),
    subtitle: document.querySelector(".landing-hero-copy p")?.textContent?.replace(/\s+/g, " ").trim(),
  }))
  if (!headerBox || headerBox.y > 1 || localeMetrics.scrolled !== "true") {
    failures.push("language switch hid sticky navigation in pinned product story")
  }
  if (!refreshedFrame || refreshedFrame.width < 1200 || refreshedFrame.y > 260 || localeMetrics.scrollY < 700) {
    failures.push("language switch lost pinned product story geometry")
  }
  if (localeMetrics.subtitle !== "说出你的分析目标，剩下的交给 Agent。") {
    failures.push("language switch did not refresh landing copy")
  }
  if (localeConsoleErrors.length) {
    failures.push(`language switch console errors: ${localeConsoleErrors.join(" | ")}`)
  }

  const footerDocs = storyPage.locator('footer a[href$="/tree/main/docs"]')
  if (
    (await footerDocs.getAttribute("target")) !== "_blank" ||
    (await footerDocs.getAttribute("rel")) !== "noreferrer"
  ) {
    failures.push("footer documentation link lost external-link safeguards")
  }
  await storyContext.close()

  const reducedContext = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    reducedMotion: "reduce",
  })
  await reducedContext.addCookies([{ name: "NEXT_LOCALE", value: "en", url: baseURL }])
  const reducedPage = await reducedContext.newPage()
  await reducedPage.goto(baseURL, { waitUntil: "domcontentloaded" })
  await reducedPage.waitForTimeout(600)
  if (!(await reducedPage.locator(".landing-static-story").isVisible())) {
    failures.push("desktop reduced-motion mode does not show product dossier")
  }
  if (await reducedPage.locator(".landing-product-frame").isVisible()) {
    failures.push("desktop reduced-motion mode leaves pinned product frame visible")
  }
  await reducedContext.close()

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
    failures.push("browser back did not return active demo visitor to landing")
  }

  await demoPage.goto(`${demoOrigin}/agent`, { waitUntil: "domcontentloaded" })
  const exitDemo = await openDemoUserMenu(demoPage)
  await exitDemo.click()
  await demoPage.waitForURL(`${demoOrigin}/`)
  const demoCookies = await demoContext.cookies()
  if (demoCookies.some((cookie) => cookie.name === "bioinfoflow_demo_access" && cookie.value)) {
    failures.push("exit demo did not clear demo access cookie")
  }
  await demoContext.close()
} finally {
  await browser.close()
}

if (failures.length) {
  console.error(failures.join("\n"))
  process.exit(1)
}

console.log("Landing visual verification passed for English and Chinese in light and dark themes from 375px to 1440px.")
