import { cn } from "@/lib/utils"

export const composerSelectorChipClassName = cn(
  "min-h-7 min-w-0 gap-1 rounded-[8px] border border-transparent bg-transparent px-2 py-0 text-[11px] font-medium leading-4 text-foreground/68 shadow-none",
  "transition-[background-color,border-color,color,transform] duration-150 hover:border-border/80 hover:bg-muted hover:text-foreground",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25 focus-visible:ring-offset-2 focus-visible:ring-offset-background active:scale-[0.98] has-[>svg]:px-2 motion-reduce:transition-none motion-reduce:active:scale-100",
)

export const composerSelectorIconClassName =
  "h-3 w-3 shrink-0 text-foreground/52"

export const composerSelectorChevronClassName =
  "h-2.5 w-2.5 shrink-0 text-foreground/42"

export const composerSelectorMenuClassName =
  "rounded-[10px] border-border bg-popover p-1 shadow-[0_8px_24px_rgba(15,15,15,0.06)]"
