import type React from "react"
import type { Metadata, Viewport } from "next"
import { Analytics } from "@vercel/analytics/next"
import { Agentation } from "agentation"
import { NextIntlClientProvider } from "next-intl"
import { getLocale, getMessages, getTranslations } from "next-intl/server"
import { AppearanceProvider } from "@/lib/appearance/provider"
import { ThemeProvider } from "@/components/theme-provider"
import "./globals.css"

const iconVersion = "20260408-3"
const siteUrl = "https://www.bioinfoflow.com"
const previewImage = {
  url: "/image.png",
  width: 1024,
  height: 1024,
  alt: "Bioinfoflow local-first agentic bioinformatics platform",
}

export async function generateMetadata(): Promise<Metadata> {
  // Locale-aware title / description / keywords so Chinese users don't
  // land on English browser tab titles and social previews. Icons and
  // generator stay locale-agnostic.
  const t = await getTranslations("metadata")
  const title = t("appTitle")
  const description = t("appDescription")

  return {
    metadataBase: new URL("https://www.bioinfoflow.com"),
    applicationName: "Bioinfoflow",
    title,
    description,
    alternates: { canonical: "/" },
    openGraph: {
      title,
      description,
      url: "/",
      siteName: "Bioinfoflow",
      images: [previewImage],
      locale: "en_US",
      alternateLocale: ["zh_CN"],
      type: "website",
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [previewImage.url],
    },
    keywords: t.raw("keywords") as string[],
    authors: [{ name: "Bioinfoflow", url: siteUrl }],
    creator: "Bioinfoflow",
    publisher: "Bioinfoflow",
    robots: {
      index: true,
      follow: true,
      googleBot: {
        index: true,
        follow: true,
        "max-image-preview": "large",
        "max-snippet": -1,
        "max-video-preview": -1,
      },
    },
    icons: {
      icon: [
        { url: `/icon-light-32x32.png?v=${iconVersion}`, type: "image/png", sizes: "32x32" },
        { url: `/icon-dark-32x32.png?v=${iconVersion}`, type: "image/png", sizes: "32x32", media: "(prefers-color-scheme: dark)" },
        { url: `/brand-icon.png?v=${iconVersion}`, type: "image/png", sizes: "512x512" },
      ],
      shortcut: `/favicon.ico?v=${iconVersion}`,
      apple: `/apple-icon.png?v=${iconVersion}`,
    },
    generator: "v0.app",
  }
}

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0a" },
  ],
}

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = await getLocale()
  const messages = await getMessages()
  const tA11y = await getTranslations("accessibility")
  const analyticsEnabled =
    process.env.VERCEL === "1" ||
    process.env.NEXT_PUBLIC_ENABLE_VERCEL_ANALYTICS === "true"

  return (
    <html lang={locale} suppressHydrationWarning>
      <body className="font-sans antialiased">
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:fixed focus:top-4 focus:left-4 focus:z-50 focus:rounded-md focus:bg-background focus:px-4 focus:py-2 focus:text-foreground focus:shadow-lg focus:outline-none"
        >
          {tA11y("skipToContent")}
        </a>
        <NextIntlClientProvider messages={messages}>
          <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
            <AppearanceProvider>{children}</AppearanceProvider>
          </ThemeProvider>
        </NextIntlClientProvider>
        {analyticsEnabled ? <Analytics /> : null}
        {process.env.NODE_ENV === "development" && <Agentation />}
      </body>
    </html>
  )
}
