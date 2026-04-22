"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useTranslations } from "next-intl"
import { cn } from "@/lib/utils"
import { NAV_ROUTES } from "@/lib/nav-routes"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

// Sidebar nav excludes "settings" — rendered separately in sidebar footer.
const sidebarNavItems = NAV_ROUTES.filter((r) => r.key !== "settings")

interface SidebarNavProps {
  collapsed: boolean
}

export function SidebarNav({ collapsed }: SidebarNavProps) {
  const pathname = usePathname()
  const tNav = useTranslations("nav")

  return (
    <nav className="space-y-0.5" aria-label="Main navigation">
      {sidebarNavItems.map((item) => {
        const isActive =
          pathname === item.href || pathname.startsWith(`${item.href}/`)

        if (collapsed) {
          return (
            <Tooltip key={item.key}>
              <TooltipTrigger asChild>
                <Link
                  href={item.href}
                  className={cn(
                    "flex h-9 w-full items-center justify-center rounded-xl border border-transparent transition-colors duration-150",
                    isActive
                      ? "border-sidebar-border/55 bg-sidebar-accent/75 text-sidebar-foreground"
                      : "text-sidebar-foreground/80 hover:bg-sidebar-accent/55 hover:text-sidebar-foreground"
                  )}
                >
                  <item.icon className="h-4 w-4" />
                </Link>
              </TooltipTrigger>
              <TooltipContent side="right">{tNav(item.key)}</TooltipContent>
            </Tooltip>
          )
        }

        return (
          <Link
            key={item.key}
            href={item.href}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "group relative flex h-10 items-center gap-3 rounded-[18px] border border-transparent px-2.5 text-sm font-semibold transition-colors duration-150",
              isActive
                ? "border-sidebar-border/55 bg-sidebar-accent/75 text-sidebar-foreground"
                : "text-sidebar-foreground/82 hover:bg-sidebar-accent/55 hover:text-sidebar-foreground"
            )}
          >
            <span
              className={cn(
                "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg transition-colors duration-150",
                isActive
                  ? "text-sidebar-foreground"
                  : "text-sidebar-foreground/76 group-hover:text-sidebar-foreground"
              )}
            >
              <item.icon className="h-4 w-4 shrink-0" />
            </span>
            <span className="truncate">{tNav(item.key)}</span>
          </Link>
        )
      })}
    </nav>
  )
}
