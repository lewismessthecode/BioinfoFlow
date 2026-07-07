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
    <nav className={cn(collapsed ? "space-y-1.5" : "space-y-1")} aria-label="Main navigation">
      {sidebarNavItems.map((item) => {
        const isActive =
          pathname === item.href || pathname.startsWith(`${item.href}/`)

        if (collapsed) {
          return (
            <Tooltip key={item.key}>
              <TooltipTrigger asChild>
                <Link
                  href={item.href}
                  aria-label={tNav(item.key)}
                  className={cn(
                    "flex h-9 w-full items-center justify-center rounded-[8px] border border-transparent transition-colors duration-150",
                    isActive
                      ? "bg-sidebar-accent text-sidebar-foreground"
                      : "text-sidebar-foreground/78 hover:bg-sidebar-accent/70 hover:text-sidebar-foreground"
                  )}
                >
                  <item.icon className="h-4 w-4" />
                </Link>
              </TooltipTrigger>
              <TooltipContent side="right" sideOffset={12}>{tNav(item.key)}</TooltipContent>
            </Tooltip>
          )
        }

        return (
          <Link
            key={item.key}
            href={item.href}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "group relative flex h-[34px] items-center gap-3 rounded-[8px] border border-transparent px-3 text-[13px] font-medium transition-colors duration-150",
              isActive
                ? "bg-sidebar-accent text-sidebar-foreground"
                : "text-sidebar-foreground/82 hover:bg-sidebar-accent/65 hover:text-sidebar-foreground"
            )}
          >
            <span
              className={cn(
                "flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-lg transition-colors duration-150",
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
