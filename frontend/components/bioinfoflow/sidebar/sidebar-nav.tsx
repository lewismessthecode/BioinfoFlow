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
    <nav className={cn(collapsed ? "space-y-1" : "space-y-0.5")} aria-label="Main navigation">
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
                  aria-current={isActive ? "page" : undefined}
                  className={cn(
                    "flex h-8 w-full items-center justify-center rounded-[7px] border border-transparent transition-colors duration-150 outline-none focus-visible:bg-sidebar-foreground/[0.06] focus-visible:ring-2 focus-visible:ring-sidebar-ring/45",
                    isActive
                      ? "bg-sidebar-foreground/[0.08] text-sidebar-foreground"
                      : "text-sidebar-foreground/78 hover:bg-sidebar-foreground/[0.055] hover:text-sidebar-foreground"
                  )}
                >
                  <item.icon className="h-3.5 w-3.5" />
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
              "group relative flex h-[30px] items-center gap-2 rounded-[7px] border border-transparent px-2.5 text-[12px] font-medium leading-none transition-colors duration-150 outline-none focus-visible:bg-sidebar-foreground/[0.06] focus-visible:ring-2 focus-visible:ring-sidebar-ring/45",
              isActive
                ? "bg-sidebar-foreground/[0.08] text-sidebar-foreground"
                : "text-sidebar-foreground/82 hover:bg-sidebar-foreground/[0.055] hover:text-sidebar-foreground"
            )}
          >
            <span
              className={cn(
                "flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[5px] transition-colors duration-150",
                isActive
                  ? "text-sidebar-foreground"
                  : "text-sidebar-foreground/76 group-hover:text-sidebar-foreground"
              )}
            >
              <item.icon className="h-3.5 w-3.5 shrink-0" />
            </span>
            <span className="truncate">{tNav(item.key)}</span>
          </Link>
        )
      })}
    </nav>
  )
}
