import { cn } from "@/lib/utils"

export const composerSelectorChipClassName = cn(
  "min-w-0 gap-1 rounded-[8px] border border-transparent bg-transparent px-2 py-0 font-medium text-foreground/68 shadow-none",
  "transition-[background-color,border-color,color,transform] duration-150 hover:border-border/80 hover:bg-muted hover:text-foreground",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25 focus-visible:ring-offset-2 focus-visible:ring-offset-background active:scale-[0.98] has-[>svg]:px-2 motion-reduce:transition-none motion-reduce:active:scale-100",
)

export const composerSelectorChevronClassName =
  "h-2.5 w-2.5 shrink-0 text-foreground/42"

export const composerSelectorMenuClassName =
  "rounded-[10px] border-border bg-popover p-1 shadow-[0_8px_24px_rgba(15,15,15,0.06)]"

export const composerSelectorMenuHeaderClassName =
  "px-2 py-1.5 text-xs font-medium leading-4 text-muted-foreground"

export const composerSelectorMenuItemClassName =
  "min-h-11 rounded-lg px-2 py-2 text-xs leading-4 lg:min-h-8"
