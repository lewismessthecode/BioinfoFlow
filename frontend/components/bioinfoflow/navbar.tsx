"use client"

import { Moon, Sun, User, LogOut, HelpCircle, Command, Menu } from "lucide-react"
import { useTranslations } from "next-intl"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { getNextAppearanceMode, useAppearance } from "@/lib/appearance/use-appearance"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu"
import { LanguageSwitcher } from "@/components/language-switcher"
import { authClient } from "@/lib/auth-client"
import { cn } from "@/lib/utils"
import { buildAnonymousViewer } from "@/lib/auth-config"
import { openInNewTab } from "@/lib/window-utils"
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
  viewer,
}: NavbarProps) {
  const router = useRouter()
  const { mode, resolvedMode, setMode } = useAppearance()
  const tUserMenu = useTranslations("userMenu")
  const tAccessibility = useTranslations("accessibility")
  const currentViewer = viewer ?? buildAnonymousViewer()

  const handleSignOut = async () => {
    if (!currentViewer.authEnabled) {
      router.push("/agent")
      return
    }

    toast.info(tUserMenu("toasts.signingOut"))

    try {
      await authClient.signOut({
        fetchOptions: {
          onSuccess: () => {
            toast.success(tUserMenu("toasts.loggedOut"))
            router.replace("/auth")
            router.refresh()
          },
        },
      })
    } catch {
      toast.error(tUserMenu("toasts.logoutFailed"))
    }
  }

  const handleHelp = () => {
    toast.info(tUserMenu("toasts.openingDocs"))
    openInNewTab("https://docs.bioinfoflow.io")
  }

  const handleKeyboardShortcuts = () => {
    toast.info(tUserMenu("toasts.keyboardShortcutsHint"))
  }

  const actionButtonClassName =
    "h-8 w-8 rounded-full border border-transparent text-foreground/78 transition-colors hover:bg-accent hover:text-foreground"

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
      <div className="flex items-center gap-1.5">
        {children}
        <LanguageSwitcher />
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

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" className={actionButtonClassName}>
              <User className="h-4 w-4" />
              <span className="sr-only">{tAccessibility("openMenu")}</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            <DropdownMenuLabel className="font-normal">
              <div className="flex flex-col gap-1">
                <p className="text-sm font-medium">{currentViewer.name}</p>
                <p className="text-xs text-muted-foreground">
                  {tUserMenu(`roles.${currentViewer.role}`)}
                </p>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={handleKeyboardShortcuts}>
              <Command className="mr-2 h-4 w-4" />
              {tUserMenu("keyboardShortcuts")}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={handleHelp}>
              <HelpCircle className="mr-2 h-4 w-4" />
              {tUserMenu("helpDocs")}
            </DropdownMenuItem>
            {currentViewer.authEnabled ? (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => void handleSignOut()}>
                  <LogOut className="mr-2 h-4 w-4" />
                  {tUserMenu("signOut")}
                </DropdownMenuItem>
              </>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      </div>
    </header>
  )
}
