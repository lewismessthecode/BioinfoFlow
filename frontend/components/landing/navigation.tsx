"use client"

import { useState, useEffect, useTransition } from "react"
import Link from "next/link"
import { Menu, X, Moon, Sun, Globe, Github } from "@/lib/icons"
import { useTheme } from "next-themes"
import { useLocale, useTranslations } from "next-intl"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"
import { Logo } from "@/components/bioinfoflow/logo"
import { locales, localeNames, type Locale } from "@/i18n/config"
import { setSecureCookie } from "@/lib/cookies"

export function Navigation() {
  const [isScrolled, setIsScrolled] = useState(false)
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const { setTheme, theme } = useTheme()
  const locale = useLocale()
  const [isPending, startTransition] = useTransition()
  const t = useTranslations("landing.nav")
  const githubUrl = "https://github.com/lewismessthecode/BioinfoFlow"

  const navLinks = [
    { label: t("product"), href: "#product" },
    { label: t("workflows"), href: "#workflows" },
    { label: t("features"), href: "#features" },
    { label: t("docs"), href: "#" },
  ]

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 10)
    }
    window.addEventListener("scroll", handleScroll, { passive: true })
    return () => window.removeEventListener("scroll", handleScroll)
  }, [])

  const handleLocaleChange = (newLocale: Locale) => {
    startTransition(() => {
      setSecureCookie("NEXT_LOCALE", newLocale, { maxAge: 31536000 })
      window.location.reload()
    })
  }

  return (
    <header
      className={cn(
        "sticky top-0 z-50 h-[72px] flex items-center transition-[background-color,border-color] duration-200",
        isScrolled
          ? "bg-background/80 backdrop-blur-md border-b border-border"
          : "bg-transparent"
      )}
    >
      <div className="container mx-auto px-6 flex items-center justify-between">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2">
          <div className="size-8 rounded-lg flex items-center justify-center">
            <Logo size={32} className="text-foreground" />
          </div>
          <span className="font-semibold text-lg tracking-tight">Bioinfoflow</span>
        </Link>

        {/* Desktop Nav */}
        <nav className="hidden md:flex items-center gap-8">
          {navLinks.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        {/* Desktop CTAs */}
        <div className="hidden md:flex items-center gap-3">
          <Button
            asChild
            variant="ghost"
            size="icon"
            className="size-8 text-muted-foreground hover:text-foreground"
          >
            <a href={githubUrl} target="_blank" rel="noreferrer">
              <Github className="size-4" />
              <span className="sr-only">GitHub</span>
            </a>
          </Button>

          {/* Language Switcher */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="size-8 text-muted-foreground hover:text-foreground"
                disabled={isPending}
              >
                <Globe className="size-4" />
                <span className="sr-only">{t("selectLanguage")}</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-40">
              {locales.map((l) => (
                <DropdownMenuItem
                  key={l}
                  onClick={() => handleLocaleChange(l)}
                  className={locale === l ? "bg-secondary" : ""}
                >
                  {localeNames[l]}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Dark Mode Toggle */}
          <Button
            variant="ghost"
            size="icon"
            className="size-8 text-muted-foreground hover:text-foreground"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          >
            <Sun className="size-4 rotate-0 scale-100 transition-transform dark:-rotate-90 dark:scale-0" />
            <Moon className="absolute size-4 rotate-90 scale-0 transition-transform dark:rotate-0 dark:scale-100" />
            <span className="sr-only">{t("toggleTheme")}</span>
          </Button>

          <Button asChild variant="ghost" size="sm" className="text-muted-foreground">
            <Link href="/auth">{t("signIn")}</Link>
          </Button>
          <Button asChild size="sm" className="rounded-full px-4">
            <Link href="/auth">{t("startFree")}</Link>
          </Button>
        </div>

        {/* Mobile Menu Button */}
        <button
          className="md:hidden p-2"
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
          aria-label={t("toggleMenu")}
        >
          {isMobileMenuOpen ? (
            <X className="size-5" />
          ) : (
            <Menu className="size-5" />
          )}
        </button>
      </div>

      {/* Mobile Menu */}
      {isMobileMenuOpen && (
        <div className="md:hidden absolute top-[72px] left-0 right-0 bg-background border-b border-border p-6">
          <nav className="flex flex-col gap-4">
            {navLinks.map((link) => (
              <Link
                key={link.label}
                href={link.href}
                className="text-base text-muted-foreground hover:text-foreground transition-colors"
                onClick={() => setIsMobileMenuOpen(false)}
              >
                {link.label}
              </Link>
            ))}

            {/* Mobile Settings Row */}
            <div className="flex items-center justify-between pt-4 border-t border-border">
              <span className="text-sm text-muted-foreground">{t("theme")}</span>
              <Button
                variant="outline"
                size="sm"
                className="gap-2"
                onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              >
                {theme === "dark" ? (
                  <>
                    <Moon className="size-4" />
                    {t("dark")}
                  </>
                ) : (
                  <>
                    <Sun className="size-4" />
                    {t("light")}
                  </>
                )}
              </Button>
            </div>

            <Button asChild variant="outline" className="w-full justify-start gap-2 bg-transparent">
              <a
                href={githubUrl}
                target="_blank"
                rel="noreferrer"
                onClick={() => setIsMobileMenuOpen(false)}
              >
                <Github className="size-4" />
                GitHub
              </a>
            </Button>

            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">{t("language")}</span>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" className="gap-2" disabled={isPending}>
                    <Globe className="size-4" />
                    {localeNames[locale as Locale]}
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-40">
                  {locales.map((l) => (
                    <DropdownMenuItem
                      key={l}
                      onClick={() => handleLocaleChange(l)}
                      className={locale === l ? "bg-secondary" : ""}
                    >
                      {localeNames[l]}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>

            <div className="flex flex-col gap-3 pt-4 border-t border-border">
              <Button asChild variant="outline" className="w-full bg-transparent">
                <Link href="/auth">{t("signIn")}</Link>
              </Button>
              <Button asChild className="w-full rounded-full">
                <Link href="/auth">{t("startFree")}</Link>
              </Button>
            </div>
          </nav>
        </div>
      )}
    </header>
  )
}
