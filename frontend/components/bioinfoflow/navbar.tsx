"use client"

import { useTransition } from "react"
import { Globe, Menu, Moon, MoreHorizontal, PartyPopper, Sun } from "@/lib/icons"
import { useLocale, useTranslations } from "next-intl"
import { Button } from "@/components/ui/button"
import { getNextAppearanceMode, useAppearance } from "@/lib/appearance/use-appearance"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"
import {
  celebratePreview,
  setCelebrationsEnabled,
  useCelebrationsEnabledPreference,
  useReducedMotionPreference,
} from "@/lib/celebrations"
import { Breadcrumbs } from "./breadcrumbs"
import { ConnectionStatus } from "./connection-status"
import type { ConnectionState } from "@/hooks/use-events"
import type { ViewerIdentity } from "@/lib/auth-config"
import { locales, localeNames, type Locale } from "@/i18n/config"
import { setSecureCookie } from "@/lib/cookies"

interface NavbarProps {
  onSidebarToggle?: () => void
  showHamburger?: boolean
  children?: React.ReactNode
  projectName?: string
  conversationTitle?: string
  connectionState?: ConnectionState
  viewer?: ViewerIdentity
}

export function Navbar({
  onSidebarToggle,
  showHamburger = false,
  children,
  projectName,
  conversationTitle,
  connectionState,
}: NavbarProps) {
  const { mode, resolvedMode, setMode } = useAppearance()
  const locale = useLocale()
  const [localePending, startLocaleTransition] = useTransition()
  const tAccessibility = useTranslations("accessibility")
  const tCelebrations = useTranslations("celebrations")
  const tLanguage = useTranslations("language")
  const celebrationsEnabled = useCelebrationsEnabledPreference()
  const reducedMotion = useReducedMotionPreference()
  const handleLocaleChange = (nextLocale: Locale) => {
    if (nextLocale === locale) return
    startLocaleTransition(() => {
      setSecureCookie("NEXT_LOCALE", nextLocale, { maxAge: 31536000 })
      window.location.reload()
    })
  }

  const actionButtonClassName =
    "h-8 w-8 rounded-[8px] border border-transparent text-foreground/70 transition-colors hover:bg-accent hover:text-foreground focus-visible:bg-accent"

  return (
    <header className="shrink-0 border-b border-border/60 bg-background/95 supports-[backdrop-filter]:bg-background/90">
      <div className="flex h-11 items-center gap-3 px-3.5">
      {/* Mobile hamburger */}
      {showHamburger && onSidebarToggle && (
        <Button
          variant="ghost"
          size="icon"
          onClick={onSidebarToggle}
          className={cn(actionButtonClassName, "mr-1 shrink-0")}
          aria-label={tAccessibility("openSidebar")}
        >
          <Menu className="h-4 w-4" />
        </Button>
      )}

      {/* Breadcrumbs */}
      <div className="hidden min-w-0 items-center gap-3 sm:flex">
        <Breadcrumbs projectName={projectName} conversationTitle={conversationTitle} />
      </div>
      {connectionState && <ConnectionStatus state={connectionState} />}

      <div className="flex-1" />

      {/* Right Actions */}
      <div
        className="flex min-w-0 max-w-full items-center gap-1.5 overflow-hidden"
        data-testid="navbar-action-row"
      >
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className={actionButtonClassName}
              disabled={localePending}
              aria-label={tAccessibility("morePreferences")}
              data-navbar-action="more"
            >
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="end"
            className="w-56 rounded-lg border-border/70 p-1.5 shadow-none"
          >
            <DropdownMenuLabel className="px-2 py-1 text-xs font-medium text-muted-foreground">
              {tAccessibility("morePreferences")}
            </DropdownMenuLabel>
            <DropdownMenuItem onClick={() => setMode(getNextAppearanceMode(mode, resolvedMode))}>
              <span className="relative h-4 w-4 shrink-0">
                <Sun className="absolute h-4 w-4 rotate-0 scale-100 transition-transform dark:-rotate-90 dark:scale-0" />
                <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-transform dark:rotate-0 dark:scale-100" />
              </span>
              {tAccessibility("toggleTheme")}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="flex items-center gap-2 px-2 py-1 text-xs font-medium text-muted-foreground">
              <Globe className="h-3.5 w-3.5" />
              {tLanguage("title")}
            </DropdownMenuLabel>
            <DropdownMenuRadioGroup value={locale}>
              {locales.map((nextLocale) => (
                <DropdownMenuRadioItem
                  key={nextLocale}
                  value={nextLocale}
                  onSelect={() => handleLocaleChange(nextLocale)}
                >
                  {localeNames[nextLocale]}
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="flex items-center gap-2 px-2 py-1 text-xs font-medium text-muted-foreground">
              <PartyPopper className="h-3.5 w-3.5" />
              {tCelebrations("title")}
            </DropdownMenuLabel>
            <DropdownMenuCheckboxItem
              checked={celebrationsEnabled}
              onCheckedChange={(checked) => setCelebrationsEnabled(Boolean(checked))}
            >
              {tCelebrations("toggle")}
            </DropdownMenuCheckboxItem>
            {reducedMotion && celebrationsEnabled ? (
              <p className="px-2 py-1.5 text-xs leading-5 text-muted-foreground">
                {tCelebrations("reducedMotion")}
              </p>
            ) : null}
            <DropdownMenuItem
              onClick={() => {
                celebratePreview()
              }}
              disabled={!celebrationsEnabled || reducedMotion}
            >
              <PartyPopper className="h-4 w-4" />
              {tCelebrations("preview")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        {children}
      </div>
      </div>
    </header>
  )
}
