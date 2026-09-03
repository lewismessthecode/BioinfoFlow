"use client"

import { useEffect, useRef, useState, useTransition } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { Menu, Moon, Sun, Globe, Github } from "@/lib/icons"
import { useTheme } from "next-themes"
import { useLocale, useTranslations } from "next-intl"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet"
import { cn } from "@/lib/utils"
import { Logo } from "@/components/bioinfoflow/logo"
import { locales, localeNames, type Locale } from "@/i18n/config"
import { setSecureCookie } from "@/lib/cookies"

const githubUrl = "https://github.com/lewismessthecode/BioinfoFlow"
const docsUrl = `${githubUrl}/tree/main/docs`

type NavigationLink = {
  label: string
  href: string
  external?: boolean
}

export function Navigation() {
  const [isScrolled, setIsScrolled] = useState(false)
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false)
  const menuButtonRef = useRef<HTMLButtonElement>(null)
  const { setTheme, theme } = useTheme()
  const locale = useLocale()
  const router = useRouter()
  const [isPending, startTransition] = useTransition()
  const t = useTranslations("landing.nav")

  const navLinks: NavigationLink[] = [
    { label: t("product"), href: "#product" },
    { label: t("workflows"), href: "#features" },
    { label: t("security"), href: "#security" },
    { label: t("docs"), href: docsUrl, external: true },
  ]

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 10)
    }
    const frame = window.requestAnimationFrame(handleScroll)

    handleScroll()
    window.addEventListener("scroll", handleScroll, { passive: true })
    window.addEventListener("pageshow", handleScroll)

    return () => {
      window.cancelAnimationFrame(frame)
      window.removeEventListener("scroll", handleScroll)
      window.removeEventListener("pageshow", handleScroll)
    }
  }, [])

  useEffect(() => {
    const desktopMedia = window.matchMedia("(min-width: 1024px)")
    const closeOnDesktop = () => {
      if (desktopMedia.matches) setIsMobileMenuOpen(false)
    }

    closeOnDesktop()
    desktopMedia.addEventListener("change", closeOnDesktop)
    return () => desktopMedia.removeEventListener("change", closeOnDesktop)
  }, [])

  const handleLocaleChange = (newLocale: Locale) => {
    if (newLocale === locale) return

    setSecureCookie("NEXT_LOCALE", newLocale, { maxAge: 31536000 })
    setIsMobileMenuOpen(false)
    startTransition(() => {
      router.refresh()
    })
  }

  const closeMobileMenu = () => setIsMobileMenuOpen(false)

  return (
    <header
      data-scrolled={isScrolled}
      className={cn(
        "landing-navigation sticky top-0 z-50 flex h-16 items-center border-b transition-[background-color,border-color,box-shadow] duration-200",
        isScrolled
          ? "border-border bg-background/92 shadow-[0_1px_0_color-mix(in_srgb,var(--brand-accent)_10%,transparent)] backdrop-blur-xl"
          : "border-border/70 bg-background/96"
      )}
    >
      <div className="mx-auto flex w-full max-w-[1440px] items-center justify-between px-5 md:px-8">
        <Link
          href="/"
          className="flex items-center gap-2.5 rounded-sm focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-[var(--brand-accent)]"
        >
          <div className="flex size-7 items-center justify-center">
            <Logo size={28} className="text-foreground" />
          </div>
          <span className="text-sm font-semibold tracking-[-0.02em]">Bioinfoflow</span>
        </Link>

        <nav aria-label={t("menu")} className="absolute left-1/2 hidden -translate-x-1/2 items-center gap-7 lg:flex">
          {navLinks.map((link) =>
            link.external ? (
              <a
                key={link.label}
                href={link.href}
                target="_blank"
                rel="noreferrer"
                className="landing-nav-link"
              >
                {link.label}
              </a>
            ) : (
              <Link key={link.label} href={link.href} className="landing-nav-link">
                {link.label}
              </Link>
            )
          )}
        </nav>

        <div className="hidden items-center gap-1.5 lg:flex">
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

          <DropdownMenu modal={false}>
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
              {locales.map((language) => (
                <DropdownMenuItem
                  key={language}
                  onClick={() => handleLocaleChange(language)}
                  className={locale === language ? "bg-secondary" : ""}
                >
                  {localeNames[language]}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>

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

        <Sheet open={isMobileMenuOpen} onOpenChange={setIsMobileMenuOpen}>
          <div className="flex items-center gap-1.5 lg:hidden">
            <Button asChild size="sm" className="hidden rounded-md px-3 shadow-none min-[420px]:inline-flex">
              <Link href="/auth">{t("startFree")}</Link>
            </Button>
            <SheetTrigger asChild>
              <button
                ref={menuButtonRef}
                type="button"
                className="flex size-11 items-center justify-center rounded-md text-foreground transition-colors hover:bg-secondary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-accent)]"
                aria-label={t("toggleMenu")}
                aria-controls="landing-navigation-menu"
                aria-expanded={isMobileMenuOpen}
              >
                <Menu className="size-5" />
              </button>
            </SheetTrigger>
          </div>

          <SheetContent
            side="top"
            id="landing-navigation-menu"
            closeLabel={t("closeMenu")}
            className="landing-toolbar-panel max-h-[calc(100dvh-1rem)] overflow-y-auto px-5 pb-6 pt-14 lg:hidden md:px-8"
          >
            <SheetTitle className="sr-only">{t("menu")}</SheetTitle>
            <SheetDescription className="sr-only">{t("menuDescription")}</SheetDescription>
            <nav aria-label={t("menu")} className="mx-auto grid max-w-[1440px] gap-5">
              <div className="grid gap-1 border-y border-border py-3">
                {navLinks.map((link) =>
                  link.external ? (
                    <a
                      key={link.label}
                      href={link.href}
                      target="_blank"
                      rel="noreferrer"
                      className="landing-menu-link"
                      onClick={closeMobileMenu}
                    >
                      {link.label}
                    </a>
                  ) : (
                    <Link key={link.label} href={link.href} className="landing-menu-link" onClick={closeMobileMenu}>
                      {link.label}
                    </Link>
                  )
                )}
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="flex items-center justify-between gap-4">
                  <span className="text-sm text-muted-foreground">{t("theme")}</span>
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-2 bg-transparent"
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

                <div className="flex items-center justify-between gap-4">
                  <span className="text-sm text-muted-foreground">{t("language")}</span>
                  <DropdownMenu modal={false}>
                    <DropdownMenuTrigger asChild>
                      <Button variant="outline" size="sm" className="gap-2 bg-transparent" disabled={isPending}>
                        <Globe className="size-4" />
                        {localeNames[locale as Locale]}
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-40">
                      {locales.map((language) => (
                        <DropdownMenuItem
                          key={language}
                          onClick={() => handleLocaleChange(language)}
                          className={locale === language ? "bg-secondary" : ""}
                        >
                          {localeNames[language]}
                        </DropdownMenuItem>
                      ))}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </div>

              <div className="grid gap-3 border-t border-border pt-5 sm:grid-cols-3">
                <Button asChild variant="outline" className="w-full justify-start gap-2 bg-transparent">
                  <a href={githubUrl} target="_blank" rel="noreferrer" onClick={closeMobileMenu}>
                    <Github className="size-4" />
                    GitHub
                  </a>
                </Button>
                <Button asChild variant="outline" className="w-full bg-transparent">
                  <Link href="/auth" onClick={closeMobileMenu}>{t("signIn")}</Link>
                </Button>
                <Button asChild className="w-full rounded-md">
                  <Link href="/auth" onClick={closeMobileMenu}>{t("startFree")}</Link>
                </Button>
              </div>
            </nav>
          </SheetContent>
        </Sheet>
      </div>
    </header>
  )
}
