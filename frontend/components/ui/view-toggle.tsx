"use client"

import { List, LayoutGrid } from "@/lib/icons"
import { cn } from "@/lib/utils"

export type ViewMode = "cards" | "list"

interface ViewToggleProps {
  view: ViewMode
  onViewChange: (view: ViewMode) => void
  listLabel?: string
  cardsLabel?: string
}

export function ViewToggle({ view, onViewChange, listLabel = "List", cardsLabel = "Cards" }: ViewToggleProps) {
  return (
    <div className="inline-flex items-center rounded-lg border border-border bg-background p-0.5">
      <button
        type="button"
        onClick={() => onViewChange("list")}
        className={cn(
          "inline-flex size-8 items-center justify-center rounded-md transition-[background-color,box-shadow,color,transform] duration-150 outline-none active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-ring/45",
          view === "list"
            ? "bg-secondary text-foreground shadow-xs"
            : "text-muted-foreground hover:bg-accent hover:text-foreground",
        )}
        aria-label={listLabel}
      >
        <List className="h-4 w-4" />
      </button>
      <button
        type="button"
        onClick={() => onViewChange("cards")}
        className={cn(
          "inline-flex size-8 items-center justify-center rounded-md transition-[background-color,box-shadow,color,transform] duration-150 outline-none active:scale-[0.98] focus-visible:ring-2 focus-visible:ring-ring/45",
          view === "cards"
            ? "bg-secondary text-foreground shadow-xs"
            : "text-muted-foreground hover:bg-accent hover:text-foreground",
        )}
        aria-label={cardsLabel}
      >
        <LayoutGrid className="h-4 w-4" />
      </button>
    </div>
  )
}
