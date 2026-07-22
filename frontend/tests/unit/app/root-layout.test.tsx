import { renderToStaticMarkup } from "react-dom/server"
import { afterEach, describe, expect, it, vi } from "vitest"

vi.mock("@vercel/analytics/next", () => ({
  Analytics: () => <div data-testid="vercel-analytics" />,
}))

vi.mock("agentation", () => ({ Agentation: () => null }))
vi.mock("next/script", () => ({
  default: ({ src }: { src: string }) => <div data-runtime-script={src} />,
}))
vi.mock("next-intl", () => ({
  NextIntlClientProvider: ({ children }: { children: React.ReactNode }) => children,
}))
vi.mock("next-intl/server", () => ({
  getLocale: async () => "en",
  getMessages: async () => ({}),
  getTranslations: async () => (key: string) => key,
}))
vi.mock("@/lib/appearance/provider", () => ({
  AppearanceProvider: ({ children }: { children: React.ReactNode }) => children,
}))
vi.mock("@/components/theme-provider", () => ({
  ThemeProvider: ({ children }: { children: React.ReactNode }) => children,
}))

import RootLayout from "@/app/layout"

describe("RootLayout analytics gate", () => {
  afterEach(() => {
    delete process.env.VERCEL
    delete process.env.NEXT_PUBLIC_ENABLE_VERCEL_ANALYTICS
  })

  it("does not render Vercel Analytics in self-hosted deployments by default", async () => {
    const html = renderToStaticMarkup(
      await RootLayout({ children: <main>content</main> }),
    )

    expect(html).not.toContain('data-testid="vercel-analytics"')
    expect(html).toContain('data-runtime-script="/runtime-config.js"')
  })

  it.each([
    ["VERCEL", "1"],
    ["NEXT_PUBLIC_ENABLE_VERCEL_ANALYTICS", "true"],
  ])("renders Vercel Analytics when %s=%s", async (name, value) => {
    process.env[name] = value

    const html = renderToStaticMarkup(
      await RootLayout({ children: <main>content</main> }),
    )

    expect(html).toContain('data-testid="vercel-analytics"')
  })
})
