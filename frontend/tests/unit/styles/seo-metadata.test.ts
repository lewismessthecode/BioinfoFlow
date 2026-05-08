import { existsSync, readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

describe("public SEO metadata", () => {
  it("publishes canonical, Open Graph, and Twitter metadata for the Vercel landing page", () => {
    const source = readFileSync(resolve(process.cwd(), "app/layout.tsx"), "utf8")

    expect(source).toContain('metadataBase: new URL("https://www.bioinfoflow.com")')
    expect(source).toContain('applicationName: "Bioinfoflow"')
    expect(source).toContain('alternates: { canonical: "/" }')
    expect(source).toContain("openGraph:")
    expect(source).toContain('siteName: "Bioinfoflow"')
    expect(source).toContain('url: "/"')
    expect(source).toContain('type: "website"')
    expect(source).toContain("twitter:")
    expect(source).toContain('card: "summary_large_image"')
  })

  it("allows crawlers to index the public site and exposes a sitemap", () => {
    const robotsPath = resolve(process.cwd(), "app/robots.ts")
    const sitemapPath = resolve(process.cwd(), "app/sitemap.ts")

    expect(existsSync(robotsPath)).toBe(true)
    expect(existsSync(sitemapPath)).toBe(true)

    const robotsSource = readFileSync(robotsPath, "utf8")
    const sitemapSource = readFileSync(sitemapPath, "utf8")

    expect(robotsSource).toContain("rules:")
    expect(robotsSource).toContain('allow: "/"')
    expect(robotsSource).toContain('sitemap: "https://www.bioinfoflow.com/sitemap.xml"')
    expect(sitemapSource).toContain('url: "https://www.bioinfoflow.com"')
    expect(sitemapSource).toContain('changeFrequency: "weekly"')
  })

  it("adds structured data that reinforces the exact Bioinfoflow brand query", () => {
    const source = readFileSync(resolve(process.cwd(), "app/page.tsx"), "utf8")

    expect(source).toContain('const productJsonLd = {')
    expect(source).toContain('"@type": "SoftwareApplication"')
    expect(source).toContain('name: "Bioinfoflow"')
    expect(source).toContain('url: "https://www.bioinfoflow.com"')
    expect(source).toContain('applicationCategory: "ScienceApplication"')
  })

  it("uses Bioinfoflow as the first landing-page headline in every locale", () => {
    const enMessages = JSON.parse(readFileSync(resolve(process.cwd(), "messages/en.json"), "utf8"))
    const zhMessages = JSON.parse(readFileSync(resolve(process.cwd(), "messages/zh-CN.json"), "utf8"))

    expect(enMessages.landing.hero.title).toBe("Bioinfoflow")
    expect(zhMessages.landing.hero.title).toBe("Bioinfoflow")
  })
})
