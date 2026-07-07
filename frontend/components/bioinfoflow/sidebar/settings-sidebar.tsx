"use client"

import { useMemo, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useTranslations } from "next-intl"
import { ArrowLeft, Search } from "lucide-react"
import { cn } from "@/lib/utils"
import { UserMenu } from "@/components/bioinfoflow/user-menu"
import type { ViewerIdentity } from "@/lib/auth-config"
import {
  SETTINGS_NAV_ITEMS,
  filterSettingsNavItems,
  groupSettingsNavItems,
  type SettingsSectionKey,
} from "@/lib/settings-nav"
import { readSettingsReturnPath } from "@/lib/settings-return-path"

interface SettingsSidebarProps {
  activeSection: SettingsSectionKey
  viewer?: ViewerIdentity
  canManageMembers: boolean
  canManageRegistries: boolean
}

export function SettingsSidebar({
  activeSection,
  viewer,
  canManageMembers,
  canManageRegistries,
}: SettingsSidebarProps) {
  const router = useRouter()
  const t = useTranslations("settings")
  const tSidebar = useTranslations("settings.sidebar")
  const [query, setQuery] = useState("")

  const visibleItems = useMemo(
    () =>
      filterSettingsNavItems(SETTINGS_NAV_ITEMS, {
        canManageMembers,
        canManageRegistries,
      }),
    [canManageMembers, canManageRegistries],
  )

  const filteredItems = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase()
    if (!normalized) return visibleItems
    return visibleItems.filter((item) => {
      const label = t(`nav.${item.key}`).toLocaleLowerCase()
      return label.includes(normalized)
    })
  }, [visibleItems, query, t])

  const groups = useMemo(() => groupSettingsNavItems(filteredItems), [
    filteredItems,
  ])

  const handleBackToApp = () => {
    router.push(readSettingsReturnPath())
  }

  return (
    <aside
      className="flex h-full min-h-0 w-full flex-col overflow-hidden border-r border-sidebar-border bg-sidebar text-sidebar-foreground"
      aria-label={tSidebar("ariaLabel")}
    >
      <div className="flex h-11 shrink-0 items-center px-3">
        <button
          type="button"
          onClick={handleBackToApp}
          className="group flex h-8 w-full items-center gap-2 rounded-[7px] border border-transparent px-2 text-left text-[12px] font-medium text-sidebar-foreground/82 transition-colors hover:bg-sidebar-foreground/[0.055] hover:text-sidebar-foreground"
        >
          <ArrowLeft className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">{tSidebar("backToApp")}</span>
        </button>
      </div>

      <div className="px-3 pb-2 pt-1">
        <label className="flex items-center gap-2 rounded-[7px] border border-sidebar-border/60 bg-sidebar-foreground/[0.03] px-2.5 py-1.5 text-[12px] text-sidebar-foreground/72 focus-within:border-sidebar-border focus-within:bg-sidebar-foreground/[0.05]">
          <Search className="h-3.5 w-3.5 shrink-0 text-sidebar-foreground/60" />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={tSidebar("searchPlaceholder")}
            aria-label={tSidebar("searchPlaceholder")}
            className="w-full bg-transparent text-[12px] text-sidebar-foreground placeholder:text-sidebar-foreground/50 focus:outline-none"
          />
        </label>
      </div>

      <nav
        className="min-h-0 flex-1 overflow-y-auto px-2.5 pb-3"
        aria-label={tSidebar("ariaLabel")}
      >
        {groups.length === 0 ? (
          <p className="px-2 py-3 text-[12px] text-sidebar-foreground/60">
            {tSidebar("noResults")}
          </p>
        ) : (
          groups.map(({ group, items }) => (
            <div key={group} className="mb-3 last:mb-0">
              <div className="px-2 pb-1 pt-2 text-[11px] font-medium uppercase tracking-[0.06em] text-sidebar-foreground/56">
                {tSidebar(`groups.${group}`)}
              </div>
              <ul className="space-y-0.5">
                {items.map((item) => {
                  const isActive = item.key === activeSection
                  const href =
                    item.key === "account"
                      ? "/settings"
                      : `/settings?section=${item.key}`
                  return (
                    <li key={item.key}>
                      <Link
                        href={href}
                        replace
                        aria-current={isActive ? "page" : undefined}
                        className={cn(
                          "group flex h-[30px] items-center gap-2 rounded-[7px] border border-transparent px-2.5 text-[12px] font-medium leading-none transition-colors duration-150",
                          isActive
                            ? "bg-sidebar-foreground/[0.08] text-sidebar-foreground"
                            : "text-sidebar-foreground/82 hover:bg-sidebar-foreground/[0.055] hover:text-sidebar-foreground",
                        )}
                      >
                        <span
                          className={cn(
                            "flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[5px] transition-colors duration-150",
                            isActive
                              ? "text-sidebar-foreground"
                              : "text-sidebar-foreground/76 group-hover:text-sidebar-foreground",
                          )}
                        >
                          <item.icon className="h-3.5 w-3.5 shrink-0" />
                        </span>
                        <span className="truncate">{t(`nav.${item.key}`)}</span>
                      </Link>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))
        )}
      </nav>

      <div className="shrink-0 border-t border-sidebar-border/60 bg-sidebar px-2.5 py-2.5">
        <UserMenu collapsed={false} viewer={viewer} />
      </div>
    </aside>
  )
}
