import { chromium } from "@playwright/test"
import { mkdir } from "node:fs/promises"
import path from "node:path"

const baseURL = process.env.LANDING_REVIEW_BASE_URL || "http://localhost:3104/landing-preview"
const outputDir = path.resolve(
  process.env.LANDING_REVIEW_OUTPUT || ".landing-review"
)

await mkdir(outputDir, { recursive: true })

const browser = await chromium.launch({ headless: true })

async function capture({ name, locale, theme, viewport, scrollY = 0, scrollToBottom = false, reducedMotion = "no-preference", fullPage = false }) {
  const context = await browser.newContext({
    viewport,
    deviceScaleFactor: 1,
    colorScheme: theme,
    reducedMotion,
  })
  await context.addCookies([{ name: "NEXT_LOCALE", value: locale, url: baseURL }])
  const page = await context.newPage()
  await page.addInitScript((selectedTheme) => {
    localStorage.setItem("theme", selectedTheme)
    document.documentElement.classList.toggle("dark", selectedTheme === "dark")
    document.documentElement.style.colorScheme = selectedTheme
  }, theme)
  await page.goto(baseURL, { waitUntil: "domcontentloaded" })
  await page.waitForTimeout(1200)
  await page.addStyleTag({
    content: `nextjs-portal, [data-agentation-root], [data-agentation-toolbar], [class*="toolbarContainer"] { display: none !important; }`,
  })
  await page.evaluate(() => {
    document.querySelectorAll("nextjs-portal").forEach((element) => element.remove())
    document.querySelectorAll("body *").forEach((element) => {
      const style = getComputedStyle(element)
      const rect = element.getBoundingClientRect()
      if (
        style.position === "fixed" &&
        window.innerWidth - rect.right < 32 &&
        window.innerHeight - rect.bottom < 32 &&
        rect.width < 96 &&
        rect.height < 96
      ) {
        element.remove()
      }
    })
  })
  if (scrollToBottom) {
    await page.evaluate(() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "instant" }))
    await page.waitForTimeout(500)
  } else if (scrollY) {
    await page.evaluate((y) => window.scrollTo({ top: y, behavior: "instant" }), scrollY)
    await page.waitForTimeout(500)
  }
  await page.screenshot({
    path: path.join(outputDir, `${name}.png`),
    fullPage,
    animations: "disabled",
  })
  await context.close()
}

try {
  await capture({ name: "desktop-wide-hero", locale: "zh-CN", theme: "light", viewport: { width: 2048, height: 1170 } })
  await capture({ name: "desktop-light-hero", locale: "en", theme: "light", viewport: { width: 1440, height: 900 } })
  await capture({ name: "desktop-light-product", locale: "en", theme: "light", viewport: { width: 1440, height: 900 }, scrollY: 1050 })
  await capture({ name: "desktop-zh-product", locale: "zh-CN", theme: "light", viewport: { width: 1440, height: 900 }, scrollY: 1050 })
  await capture({ name: "desktop-light-story", locale: "en", theme: "light", viewport: { width: 1440, height: 900 }, scrollY: 2700 })
  await capture({ name: "desktop-zh-capabilities", locale: "zh-CN", theme: "light", viewport: { width: 1440, height: 900 }, scrollY: 5100 })
  await capture({ name: "desktop-dark-hero", locale: "en", theme: "dark", viewport: { width: 1440, height: 900 } })
  await capture({ name: "desktop-dark-product", locale: "en", theme: "dark", viewport: { width: 1440, height: 900 }, scrollY: 1050 })
  await capture({ name: "desktop-light-footer", locale: "zh-CN", theme: "light", viewport: { width: 1440, height: 900 }, scrollToBottom: true })
  await capture({ name: "desktop-dark-footer", locale: "zh-CN", theme: "dark", viewport: { width: 1440, height: 900 }, scrollToBottom: true })
  await capture({ name: "desktop-zh-hero", locale: "zh-CN", theme: "light", viewport: { width: 1440, height: 900 } })
  await capture({ name: "mobile-light", locale: "en", theme: "light", viewport: { width: 390, height: 844 }, reducedMotion: "reduce", fullPage: true })
  await capture({ name: "mobile-dark", locale: "zh-CN", theme: "dark", viewport: { width: 390, height: 844 }, reducedMotion: "reduce", fullPage: true })
} finally {
  await browser.close()
}
