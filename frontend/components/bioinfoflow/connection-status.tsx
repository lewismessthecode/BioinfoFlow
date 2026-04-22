"use client"

import { useTranslations } from "next-intl"

import { cn } from "@/lib/utils"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { ConnectionState } from "@/hooks/use-events"

interface ConnectionStatusProps {
  state: ConnectionState
}

type ConnectionStateConfig = {
  color: string
  labelKey: "connecting" | "connected" | "reconnecting" | "disconnected"
  animate?: string
  showLabel: boolean
}

const stateConfig: Record<ConnectionState, ConnectionStateConfig> = {
  connecting: {
    color: "bg-warning",
    labelKey: "connecting",
    animate: "animate-pulse motion-reduce:animate-none",
    showLabel: true,
  },
  connected: {
    color: "bg-success",
    labelKey: "connected",
    showLabel: false,
  },
  reconnecting: {
    color: "bg-warning",
    labelKey: "reconnecting",
    animate: "animate-pulse motion-reduce:animate-none",
    showLabel: true,
  },
  disconnected: {
    color: "bg-muted-foreground/50",
    labelKey: "disconnected",
    showLabel: true,
  },
}

export function ConnectionStatus({ state }: ConnectionStatusProps) {
  const t = useTranslations("connectionStatus")
  const config = stateConfig[state]
  const label = t(config.labelKey)

  return (
    <Tooltip>
      {/* A button makes the trigger focusable and screen-reader visible.
          asChild + <div> (the previous shape) left the trigger silent
          when state=connected, so keyboard users and AT couldn't read
          the connection state at all. */}
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={`${t("label")}: ${label}`}
          className="flex items-center gap-1.5 px-1.5 py-1 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span
            aria-hidden="true"
            className={cn(
              "h-2 w-2 rounded-full transition-colors duration-300",
              config.color,
              config.animate,
            )}
          />
          {config.showLabel && (
            <span
              className={cn(
                "text-xs text-muted-foreground transition-opacity duration-200",
                config.animate && "text-warning",
              )}
            >
              {label}
            </span>
          )}
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom">
        <span className="text-xs">{label}</span>
      </TooltipContent>
    </Tooltip>
  )
}
