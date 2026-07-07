import { cn } from "@/lib/utils"

export const composerSelectorChipClassName = cn(
  "h-8 min-w-0 gap-1.5 rounded-[6px] border border-transparent bg-transparent px-2 py-0 text-[12px] font-medium leading-none text-foreground/68 shadow-none",
  "transition-[background-color,border-color,color,transform] duration-150 hover:border-border hover:bg-muted hover:text-foreground",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25 focus-visible:ring-offset-2 focus-visible:ring-offset-background active:scale-[0.98] has-[>svg]:px-2",
)

export const composerSelectorIconClassName =
  "h-3.5 w-3.5 shrink-0 text-foreground/52"

export const composerSelectorChevronClassName =
  "h-3 w-3 shrink-0 text-foreground/42"

export const composerSelectorMenuClassName =
  "rounded-xl border-border bg-popover p-1.5 shadow-[var(--composer-shadow)]"

export const composerModeMarkerClassName = {
  execution: "bg-[#346538]",
  plan: "bg-[#956400]",
} as const

export const composerModeToneClassName = {
  execution: "border-[#dbe8d8] bg-[#edf3ec] text-[#346538] hover:border-[#cadcc5] hover:bg-[#e4eddf] hover:text-[#294f2c]",
  plan: "border-[#eadfca] bg-[#fbf3db] text-[#956400] hover:border-[#dfd0b4] hover:bg-[#f6e9c7] hover:text-[#744d00]",
} as const
