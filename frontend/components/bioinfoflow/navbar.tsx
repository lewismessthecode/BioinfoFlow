"use client"

import { Menu, Moon, PartyPopper, Sun } from "lucide-react"
import { useTranslations } from "next-intl"
import { Button } from "@/components/ui/button"
import { getNextAppearanceMode, useAppearance } from "@/lib/appearance/use-appearance"
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
  DropdownMenuItem,
  DropdownMenuLabel,
} from "@/components/ui/dropdown-menu"
import { LanguageSwitcher } from "@/components/language-switcher"
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
  const tAccessibility = useTranslations("accessibility")
  const tCelebrations = useTranslations("celebrations")
  const celebrationsEnabled = useCelebrationsEnabledPreference()
  const reducedMotion = useReducedMotionPreference()
  const celebrationStateLabel = reducedMotion && celebrationsEnabled
    ? tAccessibility("celebrationsPaused")
    : celebrationsEnabled
      ? tAccessibility("celebrationsOn")
      : tAccessibility("celebrationsOff")
  const celebrationMenuLabel = tAccessibility("celebrationsMenuState", {
    state: celebrationStateLabel,
  })

  const actionButtonClassName =
    "h-8 w-8 rounded-lg border border-transparent text-foreground/78 transition-colors hover:bg-accent hover:text-foreground"

  return (
    <header className="shrink-0 border-b border-border/45 bg-background/88 backdrop-blur-xl supports-[backdrop-filter]:bg-background/78">
      <div className="flex h-11 items-center gap-3 px-4">
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
      <div className="flex min-w-0 items-center gap-3">
        <Breadcrumbs projectName={projectName} conversationTitle={conversationTitle} />
      </div>
      {connectionState && <ConnectionStatus state={connectionState} />}

      <div className="flex-1" />

      {/* Right Actions */}
      <div className="flex items-center gap-1.5" data-testid="navbar-action-row">
        <LanguageSwitcher />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className={cn(
                actionButtonClassName,
                celebrationsEnabled
                  ? "bg-primary/10 text-primary hover:bg-primary/15 hover:text-primary"
                  : "text-muted-foreground hover:text-foreground",
              )}
              title={celebrationMenuLabel}
            >
              <PartyPopper className="h-4 w-4" />
              <span className="sr-only">{celebrationMenuLabel}</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            <DropdownMenuLabel>{tCelebrations("title")}</DropdownMenuLabel>
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
        <Button
          variant="ghost"
          size="icon"
          className={cn(actionButtonClassName, "relative")}
          onClick={() => setMode(getNextAppearanceMode(mode, resolvedMode))}
        >
          <Sun className="h-4 w-4 rotate-0 scale-100 transition-transform dark:-rotate-90 dark:scale-0" />
          <Moon className="absolute h-4 w-4 rotate-90 scale-0 transition-transform dark:rotate-0 dark:scale-100" />
          <span className="sr-only">{tAccessibility("toggleTheme")}</span>
        </Button>
        {children}
      </div>
      </div>
    </header>
  )
}
