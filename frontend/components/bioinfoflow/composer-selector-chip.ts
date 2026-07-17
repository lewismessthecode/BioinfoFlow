import { cn } from "@/lib/utils"

export const composerSelectorChipClassName = cn(
  "min-h-7 min-w-0 gap-1 rounded-[8px] border border-transparent bg-transparent px-2 py-0 text-[11px] font-medium leading-4 text-foreground/68 shadow-none",
  "transition-[background-color,border-color,color,transform] duration-150 hover:border-border/80 hover:bg-muted hover:text-foreground",
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25 focus-visible:ring-offset-2 focus-visible:ring-offset-background active:scale-[0.98] has-[>svg]:px-2 motion-reduce:transition-none motion-reduce:active:scale-100",
)

export const composerInlineTokenClassName = cn(
  "inline-flex min-h-6 max-w-full min-w-0 items-center gap-1 rounded-[6px] border border-border/55 bg-foreground/[0.045] px-1.5 py-0.5 text-[12px] font-medium leading-4 text-foreground/78",
  "transition-[background-color,border-color,color] duration-150 hover:border-border/80 hover:bg-foreground/[0.065] hover:text-foreground",
)

export const composerSelectorIconClassName =
  "h-3 w-3 shrink-0 text-foreground/52"

export const composerSelectorChevronClassName =
  "h-2.5 w-2.5 shrink-0 text-foreground/42"

export const composerSelectorMenuClassName =
  "rounded-[10px] border-border bg-popover p-1 shadow-[0_8px_24px_rgba(15,15,15,0.06)]"

export const composerModeMarkerClassName = {
  execution: "bg-[#3a9b5b] dark:bg-[#58c486]",
  plan: "bg-[#b87924] dark:bg-[#ffbd68]",
} as const

export const composerModeToneClassName = {
  execution: "border-[#c7e4ce] bg-[#e3f3e7] text-[#2f8f55] hover:border-[#b5dac0] hover:bg-[#d8eedf] hover:text-[#257745] dark:border-[#23583a] dark:bg-[#173826] dark:text-[#58c486] dark:hover:border-[#2b7047] dark:hover:bg-[#1d4530]",
  plan: "border-[#ecd6b4] bg-[#f7ead3] text-[#a8651f] hover:border-[#e3c79b] hover:bg-[#f2dfbf] hover:text-[#895018] dark:border-[#704524] dark:bg-[#392516] dark:text-[#ffbd68] dark:hover:border-[#8a552a] dark:hover:bg-[#472e1b]",
} as const
