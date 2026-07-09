"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useTranslations } from "next-intl"
import { ChevronRight, FolderOpen, MessageSquare } from "@/lib/icons"
import { NAV_ROUTES } from "@/lib/nav-routes"
import { useBreadcrumbDetail } from "./breadcrumb-context"

interface BreadcrumbsProps {
  projectName?: string
  conversationTitle?: string
}

// Agent has its own branch in this component; all other routes are resolved from NAV_ROUTES.
const PAGE_ROUTES = NAV_ROUTES.filter((r) => r.key !== "agent")

function Separator() {
  return <ChevronRight className="h-3 w-3 text-muted-foreground/50 shrink-0" />
}

function BreadcrumbLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <Link
      href={href}
      className="text-muted-foreground hover:text-foreground transition-colors truncate"
    >
      {children}
    </Link>
  )
}

export function Breadcrumbs({ projectName, conversationTitle }: BreadcrumbsProps) {
  const pathname = usePathname()
  const tNav = useTranslations("nav")
  const { detail } = useBreadcrumbDetail()

  const route = PAGE_ROUTES.find(
    (r) => pathname === r.href || pathname.startsWith(`${r.href}/`),
  )
  const isAgentPage = pathname === "/agent" || pathname.startsWith("/agent/")
  const isDetailPage = route && pathname !== route.href
  const topLevelLabel = isAgentPage ? tNav("agent") : route ? tNav(route.key) : null
  const detailLabel = isAgentPage
    ? conversationTitle || null
    : isDetailPage
      ? detail?.label || null
      : null
  const detailHref = isAgentPage ? undefined : detail?.href

  if (!projectName) {
    if (!topLevelLabel) return null
    return (
      <nav aria-label="Breadcrumbs" className="flex items-center gap-1.5 text-sm min-w-0">
        <span className="text-foreground font-medium truncate">{topLevelLabel}</span>
        {detailLabel && (
          <>
            <Separator />
            {detailHref ? (
              <BreadcrumbLink href={detailHref}>
                <span className="text-foreground font-medium truncate max-w-[200px]">
                  {detailLabel}
                </span>
              </BreadcrumbLink>
            ) : (
              <span className="text-foreground font-medium truncate max-w-[200px]">
                {detailLabel}
              </span>
            )}
          </>
        )}
      </nav>
    )
  }

  return (
    <nav aria-label="Breadcrumbs" className="flex items-center gap-1.5 text-sm min-w-0">
      {/* Level 1: Project name */}
      <Link
        href="/dashboard"
        className="flex items-center gap-1.5 min-w-0 text-muted-foreground hover:text-foreground transition-colors shrink-0"
      >
        <FolderOpen className="h-3.5 w-3.5 shrink-0" />
        <span className="truncate max-w-[160px]">{projectName}</span>
      </Link>

      {/* Level 2: Agent conversation or page section */}
      {isAgentPage ? (
        conversationTitle ? (
          <>
            <Separator />
            <div className="flex items-center gap-1.5 min-w-0">
              <MessageSquare className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
              <span className="text-foreground font-medium truncate max-w-[240px]">
                {conversationTitle}
              </span>
            </div>
          </>
        ) : null
      ) : route ? (
        <>
          <Separator />
          {isDetailPage ? (
            <BreadcrumbLink href={route.href}>{tNav(route.key)}</BreadcrumbLink>
          ) : (
            <span className="text-foreground font-medium truncate">
              {tNav(route.key)}
            </span>
          )}

          {/* Level 3: Detail page entity name (from BreadcrumbContext) */}
          {isDetailPage && detail?.label && (
            <>
              <Separator />
              {detail.href ? (
                <BreadcrumbLink href={detail.href}>
                  <span className="text-foreground font-medium truncate max-w-[200px]">
                    {detail.label}
                  </span>
                </BreadcrumbLink>
              ) : (
                <span className="text-foreground font-medium truncate max-w-[200px]">
                  {detail.label}
                </span>
              )}
            </>
          )}
        </>
      ) : null}
    </nav>
  )
}
