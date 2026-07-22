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
    { label: t("workflows"), href: "#features" },
    { label: t("security"), href: "#security" },
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
        "sticky top-0 z-50 flex h-16 items-center border-b transition-[background-color,border-color] duration-200",
        isScrolled
          ? "border-border bg-background/92 backdrop-blur-xl"
          : "border-border/70 bg-background/96"
      )}
    >
      <div className="mx-auto flex w-full max-w-[1440px] items-center justify-between px-5 md:px-8">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2.5 rounded-sm focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--brand-accent)]">
          <div className="flex size-7 items-center justify-center">
            <Logo size={28} className="text-foreground" />
          </div>
          <span className="text-sm font-semibold tracking-[-0.02em]">Bioinfoflow</span>
        </Link>

        {/* Desktop Nav */}
        <nav className="absolute left-1/2 hidden -translate-x-1/2 items-center gap-7 lg:flex">
          {navLinks.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              className="relative py-2 text-xs font-medium text-muted-foreground transition-colors after:absolute after:inset-x-0 after:-bottom-3 after:h-0.5 after:origin-left after:scale-x-0 after:bg-[var(--brand-accent)] after:transition-transform hover:text-foreground hover:after:scale-x-100 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--brand-accent)]"
            >
              {link.label}
            </Link>
          ))}
        </nav>

        {/* Desktop CTAs */}
        <div className="hidden items-center gap-1.5 md:flex">
          <Button
            asChild
            variant="ghost"
            size="icon"
            className="size-8 rounded-md text-muted-foreground hover:text-foreground"
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
                className="size-8 rounded-md text-muted-foreground hover:text-foreground"
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
            className="size-8 rounded-md text-muted-foreground hover:text-foreground"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
          >
            <Sun className="size-4 rotate-0 scale-100 transition-transform dark:-rotate-90 dark:scale-0" />
            <Moon className="absolute size-4 rotate-90 scale-0 transition-transform dark:rotate-0 dark:scale-100" />
            <span className="sr-only">{t("toggleTheme")}</span>
          </Button>

          <Button asChild variant="ghost" size="sm" className="ml-1 rounded-md text-muted-foreground">
            <Link href="/auth">{t("signIn")}</Link>
          </Button>
          <Button asChild size="sm" className="rounded-md px-4 shadow-none active:translate-y-px">
            <Link href="/auth">{t("startFree")}</Link>
          </Button>
        </div>

        {/* Mobile Menu Button */}
        <button
          className="rounded-md p-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-accent)] md:hidden"
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
        <div className="absolute left-0 right-0 top-16 border-b border-border bg-background p-5 shadow-[var(--landing-shadow)] md:hidden">
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
              <Button asChild className="w-full rounded-md">
                <Link href="/auth">{t("startFree")}</Link>
              </Button>
            </div>
          </nav>
        </div>
      )}
    </header>
  )
}
