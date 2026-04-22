"use client"

import { List, LayoutGrid } from "lucide-react"
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
    <div className="flex items-center rounded-lg border border-border">
      <button
        onClick={() => onViewChange("list")}
        className={cn(
          "p-2 transition-colors",
          view === "list" ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground",
        )}
        aria-label={listLabel}
      >
        <List className="h-4 w-4" />
      </button>
      <button
        onClick={() => onViewChange("cards")}
        className={cn(
          "p-2 transition-colors",
          view === "cards" ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground",
        )}
        aria-label={cardsLabel}
      >
        <LayoutGrid className="h-4 w-4" />
      </button>
    </div>
  )
}
