import { cn } from "@/lib/utils"

export const composerSelectorChipClassName = cn(
  "h-8 min-w-0 gap-1.5 rounded-[7px] border border-border/70 bg-muted/35 px-2 py-0 text-[11px] font-medium leading-none text-muted-foreground shadow-none",
  "transition-[background-color,border-color,box-shadow,color,transform] duration-150 hover:border-foreground/15 hover:bg-background hover:text-foreground",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 focus-visible:ring-offset-2 focus-visible:ring-offset-background active:scale-[0.98] has-[>svg]:px-2",
)

export const composerSelectorIconClassName =
  "h-3.5 w-3.5 shrink-0 text-muted-foreground"

export const composerSelectorChevronClassName =
  "h-3 w-3 shrink-0 text-muted-foreground/70"

export const composerSelectorMenuClassName =
  "rounded-xl border-border/70 bg-popover p-1.5 shadow-[var(--composer-shadow)]"

export const composerModeMarkerClassName = {
  execution: "bg-[#9fc9a2]",
  plan: "bg-[#c0a8dd]",
} as const
