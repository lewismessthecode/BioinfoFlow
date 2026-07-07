import { cn } from "@/lib/utils"

export const composerSelectorChipClassName = cn(
  "h-8 min-w-0 gap-1.5 rounded-[7px] border border-[#e6e5e0] bg-[#fafaf7] px-2 py-0 text-[11px] font-medium leading-none text-[#5a5852] shadow-none",
  "transition-[background-color,border-color,box-shadow,color,transform] duration-150 hover:border-[#cfcdc4] hover:bg-white hover:text-[#26251e]",
  "focus-visible:ring-[#26251e]/20 active:scale-[0.98] has-[>svg]:px-2",
  "dark:border-border/65 dark:bg-background/80 dark:text-muted-foreground dark:hover:bg-accent/60 dark:hover:text-foreground",
)

export const composerSelectorIconClassName =
  "h-3.5 w-3.5 shrink-0 text-[#807d72] dark:text-muted-foreground"

export const composerSelectorChevronClassName =
  "h-3 w-3 shrink-0 text-[#a09c92] dark:text-muted-foreground"

export const composerSelectorMenuClassName =
  "rounded-xl border-border/70 bg-[#fffefa] p-1.5 shadow-[0_14px_34px_rgba(36,35,33,0.08)] dark:bg-popover"

export const composerModeMarkerClassName = {
  execution: "bg-[#9fc9a2]",
  plan: "bg-[#c0a8dd]",
} as const
