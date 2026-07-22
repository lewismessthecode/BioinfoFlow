import { chromium } from "@playwright/test"
import { mkdir, rm } from "node:fs/promises"
import path from "node:path"
import sharp from "sharp"

const baseURL = process.env.LANDING_CAPTURE_BASE_URL || "http://localhost:3000"
const outputDir = path.resolve(process.cwd(), "public/landing/product")
const temporaryDir = path.resolve(process.cwd(), ".landing-capture")
const stages = ["dashboard", "agent", "workflows", "runs"]
const themes = ["light", "dark"]

await mkdir(outputDir, { recursive: true })
await rm(temporaryDir, { recursive: true, force: true })
await mkdir(temporaryDir, { recursive: true })

const browser = await chromium.launch({ headless: true })

try {
  for (const theme of themes) {
    const context = await browser.newContext({
      viewport: { width: 1280, height: 720 },
      deviceScaleFactor: 2,
      colorScheme: theme,
      reducedMotion: "reduce",
    })

    await context.addCookies([
      { name: "NEXT_LOCALE", value: "en", url: baseURL },
      { name: "bioinfoflow_demo_access", value: "guest", url: baseURL },
    ])

    const page = await context.newPage()

    await page.route("**/api/v1/**", async (route) => {
      const originalUrl = new URL(route.request().url())
      if (originalUrl.pathname.endsWith("/events/stream")) {
        await route.abort()
        return
      }
      const response = await route.fetch({
        url: `http://localhost:8000${originalUrl.pathname}${originalUrl.search}`,
      })
      await route.fulfill({ response })
    })

    await page.addInitScript((selectedTheme) => {
      localStorage.setItem("theme", selectedTheme)
      document.documentElement.classList.toggle("dark", selectedTheme === "dark")
      document.documentElement.style.colorScheme = selectedTheme
    }, theme)

    for (const stage of stages) {
      await page.goto(`${baseURL}/${stage}`, { waitUntil: "domcontentloaded" })
      await page.waitForTimeout(stage === "dashboard" ? 1800 : 1000)
      await page.addStyleTag({
        content: `
          nextjs-portal,
          [data-agentation-root],
          [data-agentation-toolbar],
          [aria-label*="Agentation" i] {
            display: none !important;
          }
          * { caret-color: transparent !important; }
        `,
      })
      await page.evaluate(() => {
        document.querySelectorAll("nextjs-portal").forEach((element) => element.remove())
      })

      const pngPath = path.join(temporaryDir, `${stage}-${theme}.png`)
      const webpPath = path.join(outputDir, `${stage}-${theme}.webp`)

      await page.screenshot({
        path: pngPath,
        clip: { x: 0, y: 0, width: 1280, height: 577 },
        scale: "device",
        animations: "disabled",
      })

      const metadata = await sharp(pngPath).metadata()
      if ((metadata.width ?? 0) < 2560) {
        throw new Error(`${stage}-${theme} capture is only ${metadata.width}px wide`)
      }

      await sharp(pngPath).webp({ quality: 92, smartSubsample: true }).toFile(webpPath)
    }

    await page.unrouteAll({ behavior: "ignoreErrors" })
    await context.close()
  }
} finally {
  await browser.close()
  await rm(temporaryDir, { recursive: true, force: true })
}
