"use client"

import type { AppIcon } from "@/lib/icons"
import { Button } from "@/components/ui/button"

export type AgentActionId = "browser" | "files" | "artifacts" | "dag"

export type AgentActionCommandPort = {
  toggle: (actionId: AgentActionId) => void
}

export type AgentActionModel = {
  id: AgentActionId
  label: string
  openLabel: string
  closeLabel: string
  icon: AppIcon
  active: boolean
  pressed: boolean
  disabled?: boolean
}

export function AgentActionGroup({
  actions,
  commandPort,
}: {
  actions: readonly AgentActionModel[]
  commandPort: AgentActionCommandPort
}) {
  return (
    <>
      {actions.map((action) => {
        const Icon = action.icon
        return (
          <Button
            key={action.id}
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 rounded-[8px] border border-transparent text-foreground/70 transition-colors hover:bg-accent hover:text-foreground focus-visible:bg-accent"
            disabled={action.disabled}
            aria-label={action.pressed ? action.closeLabel : action.openLabel}
            aria-pressed={action.pressed}
            data-action-id={action.id}
            data-active={action.active ? "true" : "false"}
            data-state={action.active ? "active" : "inactive"}
            title={action.label}
            onClick={() => commandPort.toggle(action.id)}
          >
            <Icon aria-hidden="true" className="h-4 w-4" />
          </Button>
        )
      })}
    </>
  )
}
