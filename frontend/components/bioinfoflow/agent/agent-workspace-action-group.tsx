"use client"

import { useCallback, useRef, type KeyboardEvent, type ReactNode } from "react"

import { Button } from "@/components/ui/button"
import {
  Box,
  FileCode2,
  Globe,
  PanelRightClose,
  Workflow,
  X,
  type AppIcon,
} from "@/lib/icons"
import { cn } from "@/lib/utils"

export type AgentWorkspaceTab = "artifacts" | "files" | "dag" | "browser"

export type AgentWorkspaceActionGroupProps = {
  activeTab: AgentWorkspaceTab | null
  panelOpen: boolean
  labels: {
    group: string
    artifacts: string
    files: string
    dag: string
    browser: string
    openPanel: string
    closePanel: string
    closeTab: string
  }
  onOpenTab: (tab: AgentWorkspaceTab) => void
  onTogglePanel: () => void
  onCloseTab: () => void
}

const workspaceTabs: Array<{
  key: AgentWorkspaceTab
  label: keyof Pick<
    AgentWorkspaceActionGroupProps["labels"],
    "artifacts" | "files" | "dag" | "browser"
  >
  Icon: AppIcon
}> = [
  { key: "artifacts", label: "artifacts", Icon: Box },
  { key: "files", label: "files", Icon: FileCode2 },
  { key: "dag", label: "dag", Icon: Workflow },
  { key: "browser", label: "browser", Icon: Globe },
]

const iconButtonClassName =
  "h-8 w-8 shrink-0 rounded-[8px] border border-transparent bg-transparent text-foreground/70 shadow-none transition-colors hover:bg-accent/70 hover:text-foreground focus-visible:bg-accent"

export function AgentWorkspaceActionGroup({
  activeTab,
  panelOpen,
  labels,
  onOpenTab,
  onTogglePanel,
  onCloseTab,
}: AgentWorkspaceActionGroupProps) {
  const actionRefs = useRef<Record<string, HTMLButtonElement | null>>({})

  const focusAction = useCallback((action: string) => {
    actionRefs.current[action]?.focus()
  }, [])

  const handleActionKeyDown = useCallback(
    (event: KeyboardEvent<HTMLButtonElement>) => {
      const actions = ["artifacts", "files", "dag", "browser", "panel"]
      const current = event.currentTarget.dataset.workspaceAction
      if (!current) return
      const currentIndex = actions.indexOf(current)
      if (currentIndex < 0) return

      let nextIndex: number | null = null
      if (event.key === "ArrowRight" || event.key === "ArrowDown") {
        nextIndex = (currentIndex + 1) % actions.length
      } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
        nextIndex = (currentIndex - 1 + actions.length) % actions.length
      } else if (event.key === "Home") {
        nextIndex = 0
      } else if (event.key === "End") {
        nextIndex = actions.length - 1
      }

      if (nextIndex === null) return
      event.preventDefault()
      const nextAction = actions[nextIndex]
      focusAction(nextAction)
    },
    [focusAction],
  )

  return (
    <div
      className="flex min-w-0 max-w-full flex-nowrap items-center gap-1 overflow-hidden"
      data-testid="agent-workspace-action-group"
      role="group"
      aria-label={labels.group}
    >
      <span
        aria-hidden="true"
        className="mx-0.5 h-5 w-px shrink-0 bg-border/65"
        data-workspace-divider="true"
      />
      <div
        className="flex min-w-0 flex-nowrap items-center gap-0.5 overflow-hidden"
        data-workspace-tabs="true"
      >
        {workspaceTabs.map(({ key, label, Icon }) => {
          const active = panelOpen && activeTab === key
          const actionLabel = labels[label]
          return (
            <div
              key={key}
              className={cn(
                "flex h-8 min-w-0 items-center rounded-[8px] text-muted-foreground transition-colors duration-200",
                active
                  ? "bg-muted/65 text-foreground"
                  : "hover:bg-muted/35 hover:text-foreground",
              )}
              data-active={active ? "true" : "false"}
            >
              <button
                type="button"
                className="flex h-full min-w-0 shrink-0 items-center gap-1.5 rounded-[8px] px-2 text-xs font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring/25 focus-visible:ring-offset-1 focus-visible:ring-offset-background"
                aria-label={actionLabel}
                aria-pressed={active}
                title={actionLabel}
                ref={(node) => {
                  actionRefs.current[key] = node
                }}
                data-workspace-action={key}
                onKeyDown={handleActionKeyDown}
                onClick={() => onOpenTab(key)}
              >
                <Icon aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
                <span className="hidden max-w-20 truncate xl:inline">{actionLabel}</span>
              </button>
              {active ? (
                <button
                  type="button"
                  className="mr-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-background/70 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25"
                  aria-label={labels.closeTab}
                  title={labels.closeTab}
                  onClick={() => {
                    onCloseTab()
                    actionRefs.current[key]?.focus()
                  }}
                >
                  <X aria-hidden="true" className="h-3 w-3" />
                </button>
              ) : null}
            </div>
          )
        })}
      </div>

      <ActionIconButton
        label={panelOpen ? labels.closePanel : labels.openPanel}
        action="panel"
        active={panelOpen}
        onClick={onTogglePanel}
        onKeyDown={handleActionKeyDown}
        buttonRef={(node) => {
          actionRefs.current.panel = node
        }}
        icon={
          <PanelRightClose
            aria-hidden="true"
            className={cn("h-4 w-4 transition-transform", !panelOpen && "rotate-180")}
          />
        }
      />
    </div>
  )
}

function ActionIconButton({
  label,
  action,
  active = false,
  icon,
  onClick,
  onKeyDown,
  buttonRef,
}: {
  label: string
  action: "panel"
  active?: boolean
  icon: ReactNode
  onClick: () => void
  onKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => void
  buttonRef: (node: HTMLButtonElement | null) => void
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className={cn(iconButtonClassName, active && "bg-accent text-foreground")}
      aria-label={label}
      title={label}
      aria-pressed={active}
      data-workspace-action={action}
      ref={buttonRef}
      onKeyDown={onKeyDown}
      onClick={onClick}
    >
      {icon}
    </Button>
  )
}
