"use client"

import { useTranslations } from "next-intl"
import { useRouter } from "next/navigation"
import { ChevronsUpDown, Moon, Settings } from "@/lib/icons"
import { Badge } from "@/components/ui/badge"
import { getNextAppearanceMode, useAppearance } from "@/lib/appearance/use-appearance"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { authClient } from "@/lib/auth-client"
import { buildAnonymousViewer } from "@/lib/auth-config"
import { toast } from "sonner"
import type { ViewerIdentity } from "@/lib/auth-config"

interface UserMenuProps {
  collapsed: boolean
  viewer?: ViewerIdentity
}

export function UserMenu({ collapsed, viewer }: UserMenuProps) {
  const tUserMenu = useTranslations("userMenu")
  const tAccessibility = useTranslations("accessibility")
  const { mode, resolvedMode, setMode } = useAppearance()
  const router = useRouter()
  const currentViewer = viewer ?? buildAnonymousViewer()
  const userName = currentViewer.name || tUserMenu("defaultName")
  const userEmail = currentViewer.email || ""
  const userImage = currentViewer.image || null
  const userInitials = userName
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2) || "U"

  const handleLogout = async () => {
    if (!currentViewer.authEnabled) {
      router.replace("/agent")
      return
    }

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

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          className={
            collapsed
              ? "group mx-auto flex h-9 w-9 items-center justify-center rounded-[8px] border border-border/70 bg-card/90 p-0 transition-[background-color,border-color,box-shadow,transform] duration-150 hover:bg-sidebar-accent/70 motion-safe:active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-sidebar-ring/45 focus-visible:outline-none"
              : "group flex w-full items-center gap-2 rounded-[8px] border border-transparent px-2 py-1.5 transition-[background-color,border-color,box-shadow,transform] duration-150 hover:bg-sidebar-accent motion-safe:active:scale-[0.98] focus-visible:bg-sidebar-accent focus-visible:ring-2 focus-visible:ring-sidebar-ring/45 focus-visible:outline-none"
          }
          aria-label={`${userName} — ${tAccessibility("userMenu")}`}
        >
          <Avatar
            className={collapsed ? "h-7 w-7 rounded-[7px] ring-1 ring-border/60" : "h-8 w-8 rounded-[8px] ring-1 ring-border/60"}
            aria-hidden="true"
          >
            <AvatarImage src={userImage || undefined} alt="" />
            <AvatarFallback className="rounded-[8px] bg-primary/10 text-xs text-primary">
              {userInitials}
            </AvatarFallback>
          </Avatar>
          {!collapsed && (
            <>
              <span className="min-w-0 flex-1 text-left">
                <span className="block truncate text-sm font-medium text-foreground">
                  {userName}
                </span>
                <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                  {tUserMenu(`roles.${currentViewer.role}`)}
                </span>
              </span>
              <ChevronsUpDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground/80" />
            </>
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align={collapsed ? "start" : "end"}
        side={collapsed ? "right" : "top"}
        sideOffset={8}
        className="w-[220px] rounded-xl border border-border/60 p-1.5 shadow-[0_14px_34px_rgba(36,35,33,0.08)]"
      >
        {userEmail ? (
          <>
            <div className="mb-1 px-2 py-2">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <Badge variant="outline" className="rounded-[6px]">
                  {tUserMenu(`roles.${currentViewer.role}`)}
                </Badge>
                <Badge variant="secondary" className="rounded-[6px]">
                  {currentViewer.workspaceName}
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground truncate">{userEmail}</p>
            </div>
            <DropdownMenuSeparator className="mx-1" />
          </>
        ) : null}

        <DropdownMenuItem
          onClick={() => setMode(getNextAppearanceMode(mode, resolvedMode))}
          className="mx-0.5 cursor-pointer rounded-[8px] px-2.5 py-2 focus:bg-secondary"
        >
          <Moon className="mr-2.5 h-4 w-4 text-muted-foreground" />
          <span>
            {resolvedMode === "dark"
              ? tUserMenu("lightMode")
              : tUserMenu("darkMode")}
          </span>
        </DropdownMenuItem>

        <DropdownMenuItem
          onClick={() => router.push("/settings")}
          className="mx-0.5 cursor-pointer rounded-[8px] px-2.5 py-2 focus:bg-secondary"
        >
          <Settings className="mr-2.5 h-4 w-4 text-muted-foreground" />
          <span>{tUserMenu("settings")}</span>
        </DropdownMenuItem>

        {currentViewer.authEnabled ? (
          <>
            <DropdownMenuSeparator className="mx-1 my-1" />

            <DropdownMenuItem
              onClick={handleLogout}
              className="mx-0.5 cursor-pointer rounded-[8px] px-2.5 py-2 text-destructive focus:bg-destructive/10 focus:text-destructive"
            >
              <span>{tUserMenu("signOut")}</span>
            </DropdownMenuItem>
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
