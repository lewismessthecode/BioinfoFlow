"use client"

import { useTranslations } from "next-intl"
import { Bot, FileBox, FolderTree, Globe, X, type AppIcon } from "@/lib/icons"
import { cn } from "@/lib/utils"

import type { AgentTabbedPanelTab } from "./agent-tabbed-panel"

const TABS: Array<{
  key: AgentTabbedPanelTab
  labelKey: string
  iconName: string
  Icon: AppIcon
}> = [
  { key: "preview", labelKey: "tabs.artifacts", iconName: "file-box", Icon: FileBox },
  { key: "files", labelKey: "tabs.files", iconName: "folder-tree", Icon: FolderTree },
  { key: "agents", labelKey: "tabs.agents", iconName: "bot", Icon: Bot },
  { key: "browser", labelKey: "tabs.browser", iconName: "globe", Icon: Globe },
]

export function AgentWorkspaceTabs({
  activeTab,
  onActiveTabChange,
  onClose,
}: {
  activeTab: AgentTabbedPanelTab
  onActiveTabChange: (tab: AgentTabbedPanelTab) => void
  onClose: () => void
}) {
  const t = useTranslations("agentRuntime")

  const moveFocus = (nextIndex: number) => {
    const nextTab = TABS[nextIndex]?.key
    if (!nextTab) return
    onActiveTabChange(nextTab)
    window.requestAnimationFrame(() => {
      document.getElementById(`agent-sidecar-tab-${nextTab}`)?.focus()
    })
  }

  return (
    <div
      className="mr-1 flex min-w-0 items-center gap-0.5 border-r border-border/55 pr-1.5"
      role="tablist"
      aria-label={t("sidecar.title")}
      data-testid="agent-sidecar-tab-strip"
    >
      {TABS.map(({ key, labelKey, iconName, Icon }, index) => {
        const active = activeTab === key
        return (
          <div
            key={key}
            className={cn(
              "flex h-8 min-w-0 items-center rounded-[8px] text-muted-foreground transition-colors duration-200",
              active
                ? "bg-muted/65 text-foreground"
                : "hover:bg-muted/35 hover:text-foreground",
            )}
          >
            <button
              type="button"
              role="tab"
              id={`agent-sidecar-tab-${key}`}
              aria-controls={`agent-sidecar-panel-${key}`}
              aria-selected={active}
              tabIndex={active ? 0 : -1}
              onClick={() => onActiveTabChange(key)}
              onKeyDown={(event) => {
                const lastIndex = TABS.length - 1
                if (event.key === "ArrowRight" || event.key === "ArrowDown") {
                  event.preventDefault()
                  moveFocus(index === lastIndex ? 0 : index + 1)
                } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
                  event.preventDefault()
                  moveFocus(index === 0 ? lastIndex : index - 1)
                } else if (event.key === "Home") {
                  event.preventDefault()
                  moveFocus(0)
                } else if (event.key === "End") {
                  event.preventDefault()
                  moveFocus(lastIndex)
                }
              }}
              aria-label={t(labelKey)}
              className="flex h-full min-w-0 items-center gap-1.5 rounded-[8px] px-2 text-xs font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring/25 focus-visible:ring-offset-1 focus-visible:ring-offset-background"
              data-active={active}
            >
              <Icon
                className="h-3.5 w-3.5 shrink-0"
                data-icon={iconName}
                data-testid={`agent-sidecar-tab-icon-${key}`}
                aria-hidden="true"
              />
              <span className="max-w-20 truncate">{t(labelKey)}</span>
            </button>
            {active ? (
              <button
                type="button"
                className="mr-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-background/70 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25"
                onClick={(event) => {
                  event.stopPropagation()
                  onClose()
                }}
                aria-label={t("sidecar.close")}
              >
                <X className="h-3 w-3" />
              </button>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}
