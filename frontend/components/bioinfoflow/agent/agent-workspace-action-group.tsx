"use client"

import { useCallback, useRef, type KeyboardEvent, type ReactNode } from "react"
import { Button } from "@/components/ui/button"
import {
  Box,
  FileCode2,
  Globe,
  PanelRightClose,
  Plus,
  Workflow,
  type AppIcon,
} from "@/lib/icons"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"

import type { AgentWorkspaceTab } from "@/lib/agent/drawer-tabs"

export type { AgentWorkspaceTab } from "@/lib/agent/drawer-tabs"

export type AgentWorkspaceActionGroupProps = {
  panelOpen: boolean
  labels: {
    group: string
    addTab?: string
    artifacts: string
    files: string
    dag: string
    browser: string
    openPanel: string
    closePanel: string
  }
  onOpenTab: (tab: AgentWorkspaceTab) => void
  onTogglePanel: () => void
}

const workspaceTabs: Array<{ key: AgentWorkspaceTab; label: keyof AgentWorkspaceActionGroupProps["labels"]; Icon: AppIcon }> = [
  { key: "artifacts", label: "artifacts", Icon: Box },
  { key: "workspace", label: "files", Icon: FileCode2 },
  { key: "dag", label: "dag", Icon: Workflow },
  { key: "browser", label: "browser", Icon: Globe },
]

const iconButtonClassName = "h-8 w-8 shrink-0 rounded-[8px] border border-transparent bg-transparent text-foreground/70 shadow-none transition-colors hover:bg-accent/70 hover:text-foreground focus-visible:bg-accent max-xl:h-11 max-xl:w-11"

export function AgentWorkspaceActionGroup({
  panelOpen,
  labels,
  onOpenTab,
  onTogglePanel,
}: AgentWorkspaceActionGroupProps) {
  const actionRefs = useRef<Record<string, HTMLButtonElement | null>>({})
  const focusAction = useCallback((action: string) => actionRefs.current[action]?.focus(), [])
  const handleActionKeyDown = useCallback((event: KeyboardEvent<HTMLButtonElement>) => {
    const actions = ["panel"]
    const current = event.currentTarget.dataset.workspaceAction
    if (!current) return
    const index = actions.indexOf(current as "panel")
    if (index < 0) return
    const next = event.key === "ArrowRight" || event.key === "ArrowDown" ? (index + 1) % actions.length : event.key === "ArrowLeft" || event.key === "ArrowUp" ? (index - 1 + actions.length) % actions.length : event.key === "Home" ? 0 : event.key === "End" ? actions.length - 1 : null
    if (next === null) return
    event.preventDefault(); focusAction(actions[next])
  }, [focusAction])

  return (
    <div className="flex min-w-0 max-w-full flex-nowrap items-center gap-1 overflow-hidden" data-testid="agent-workspace-action-group" role="group" aria-label={labels.group}>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button type="button" variant="ghost" size="icon" className={iconButtonClassName} aria-label={labels.addTab ?? "Add tab"} title={labels.addTab ?? "Add tab"} data-testid="agent-action-add-tab">
            <Plus aria-hidden="true" className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-44">
          {workspaceTabs.map(({ key, label, Icon }) => (
            <DropdownMenuItem key={key} onSelect={() => onOpenTab(key)}>
              <Icon aria-hidden="true" /> {labels[label]}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>

      <ActionIconButton label={panelOpen ? labels.closePanel : labels.openPanel} active={panelOpen} onClick={onTogglePanel} onKeyDown={handleActionKeyDown} buttonRef={(node) => { actionRefs.current.panel = node }} icon={<PanelRightClose aria-hidden="true" className={cn("h-4 w-4 transition-transform", !panelOpen && "rotate-180")} />} />
    </div>
  )
}

function ActionIconButton({ label, active = false, icon, onClick, onKeyDown, buttonRef }: { label: string; active?: boolean; icon: ReactNode; onClick: () => void; onKeyDown: (event: KeyboardEvent<HTMLButtonElement>) => void; buttonRef: (node: HTMLButtonElement | null) => void }) {
  return <Button type="button" variant="ghost" size="icon" className={cn(iconButtonClassName, active && "bg-accent text-foreground")} aria-label={label} title={label} aria-pressed={active} data-workspace-action="panel" data-action-id="panel" ref={buttonRef} onKeyDown={onKeyDown} onClick={onClick}>{icon}</Button>
}
