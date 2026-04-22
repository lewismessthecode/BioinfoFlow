import { cn } from "@/lib/utils"
import { cva, type VariantProps } from "class-variance-authority"
import type { LucideIcon } from "lucide-react"

const iconBoxVariants = cva(
  "flex shrink-0 items-center justify-center",
  {
    variants: {
      size: {
        sm: "h-8 w-8 rounded-lg",
        md: "h-9 w-9 rounded-xl",
        lg: "h-10 w-10 rounded-xl",
        xl: "h-12 w-12 rounded-xl",
      },
      variant: {
        default: "border border-border/60 bg-secondary/50 dark:bg-secondary/30",
        gradient: "border border-border/60 bg-gradient-to-br from-secondary/70 via-background to-background shadow-sm",
        muted: "bg-muted/30",
        primary: "bg-primary/10 text-primary",
        surface: "bg-secondary",
      },
    },
    defaultVariants: {
      size: "sm",
      variant: "default",
    },
  }
)

const iconSizeMap = {
  sm: "h-3.5 w-3.5",
  md: "h-4 w-4",
  lg: "h-4.5 w-4.5",
  xl: "h-5 w-5",
} as const

export interface IconBoxProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof iconBoxVariants> {
  icon: LucideIcon
  iconClassName?: string
}

export function IconBox({
  className,
  size = "sm",
  variant,
  icon: Icon,
  iconClassName,
  ...props
}: IconBoxProps) {
  return (
    <div className={cn(iconBoxVariants({ size, variant }), className)} {...props}>
      <Icon className={cn(iconSizeMap[size ?? "sm"], "text-foreground/70", iconClassName)} />
    </div>
  )
}
