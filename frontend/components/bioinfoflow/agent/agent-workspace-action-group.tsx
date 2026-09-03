"use client"

import type { ReactNode } from "react"

import { Button } from "@/components/ui/button"
import {
  Box,
  FileCode2,
  Globe,
  MoreHorizontal,
  PanelRightClose,
  TerminalSquare,
  Workflow,
  X,
  type AppIcon,
} from "@/lib/icons"
import { cn } from "@/lib/utils"

export type AgentWorkspaceTab = "artifacts" | "files" | "dag" | "browser"

export type AgentWorkspaceActionGroupProps = {
  activeTab: AgentWorkspaceTab | null
  panelOpen: boolean
  terminalOpen?: boolean
  labels: {
    group: string
    more: string
    terminal: string
    artifacts: string
    files: string
    dag: string
    browser: string
    openPanel: string
    closePanel: string
    closeTab: string
  }
  onMore: () => void
  onToggleTerminal: () => void
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
  terminalOpen = false,
  labels,
  onMore,
  onToggleTerminal,
  onOpenTab,
  onTogglePanel,
  onCloseTab,
}: AgentWorkspaceActionGroupProps) {
  return (
    <div
      className="flex min-w-0 items-center gap-1"
      data-testid="agent-workspace-action-group"
      role="group"
      aria-label={labels.group}
    >
      <ActionIconButton
        label={labels.more}
        action="more"
        onClick={onMore}
        icon={<MoreHorizontal aria-hidden="true" className="h-4 w-4" />}
      />
      <ActionIconButton
        label={labels.terminal}
        action="terminal"
        active={terminalOpen}
        onClick={onToggleTerminal}
        icon={<TerminalSquare aria-hidden="true" className="h-4 w-4" />}
      />

      <span aria-hidden="true" className="mx-0.5 h-5 w-px shrink-0 bg-border/65" />

      <div className="flex min-w-0 items-center gap-0.5">
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
                className="flex h-full min-w-0 items-center gap-1.5 rounded-[8px] px-2 text-xs font-medium outline-none focus-visible:ring-2 focus-visible:ring-ring/25 focus-visible:ring-offset-1 focus-visible:ring-offset-background"
                aria-label={actionLabel}
                aria-pressed={active}
                data-workspace-action={key}
                onClick={() => onOpenTab(key)}
              >
                <Icon aria-hidden="true" className="h-3.5 w-3.5 shrink-0" />
                <span className="max-w-20 truncate">{actionLabel}</span>
              </button>
              {active ? (
                <button
                  type="button"
                  className="mr-1 flex h-5 w-5 shrink-0 items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-background/70 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25"
                  aria-label={labels.closeTab}
                  onClick={onCloseTab}
                >
                  <X aria-hidden="true" className="h-3 w-3" />
                </button>
              ) : null}
            </div>
          )
        })}
      </div>

      <span aria-hidden="true" className="mx-0.5 h-5 w-px shrink-0 bg-border/65" />

      <ActionIconButton
        label={panelOpen ? labels.closePanel : labels.openPanel}
        action="panel"
        active={panelOpen}
        onClick={onTogglePanel}
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
}: {
  label: string
  action: "more" | "terminal" | "panel"
  active?: boolean
  icon: ReactNode
  onClick: () => void
}) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className={cn(iconButtonClassName, active && "bg-accent text-foreground")}
      aria-label={label}
      aria-pressed={action === "more" ? undefined : active}
      data-workspace-action={action}
      onClick={onClick}
    >
      {icon}
    </Button>
  )
}
