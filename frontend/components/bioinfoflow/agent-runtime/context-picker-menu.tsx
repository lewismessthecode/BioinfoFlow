"use client"

import type { AgentRuntimeContextSearchItem } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"

type ContextPickerMenuProps = {
  open: boolean
  status: "idle" | "loading" | "ready" | "empty" | "error"
  results: AgentRuntimeContextSearchItem[]
  error?: string | null
  highlightedIndex?: number
  onSelect: (item: AgentRuntimeContextSearchItem) => void
}

export function ContextPickerMenu({
  open,
  status,
  results,
  error,
  highlightedIndex = 0,
  onSelect,
}: ContextPickerMenuProps) {
  if (!open) return null
  return (
    <div
      role="listbox"
      aria-label="Context suggestions"
      className="absolute bottom-full left-0 z-20 mb-2 w-[min(28rem,calc(100vw-2rem))] overflow-hidden rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-[0_8px_24px_rgba(15,23,42,0.08)]"
    >
      {status === "loading" ? <PickerState>Searching context…</PickerState> : null}
      {status === "empty" ? <PickerState>No matching context</PickerState> : null}
      {status === "error" ? <PickerState>{error || "Context search failed"}</PickerState> : null}
      {status === "ready"
        ? results.map((item, index) => (
            <button
              key={`${item.kind}:${item.id}`}
              type="button"
              role="option"
              aria-selected={index === highlightedIndex}
              className={cn(
                "flex w-full items-start gap-3 rounded-md px-3 py-2 text-left transition-colors",
                index === highlightedIndex
                  ? "bg-accent text-accent-foreground"
                  : "hover:bg-muted/70",
              )}
              onMouseDown={(event) => {
                event.preventDefault()
                onSelect(item)
              }}
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{item.label}</span>
                {item.detail ? (
                  <span className="block truncate text-xs text-muted-foreground">
                    {item.detail}
                  </span>
                ) : null}
              </span>
              <span className="pt-0.5 text-[10px] uppercase tracking-[0.08em] text-muted-foreground">
                {item.kind}
              </span>
            </button>
          ))
        : null}
    </div>
  )
}

function PickerState({ children }: { children: React.ReactNode }) {
  return <div className="px-3 py-3 text-sm text-muted-foreground">{children}</div>
}
