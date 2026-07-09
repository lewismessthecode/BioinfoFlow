import { cn } from "@/lib/utils"
import { cva, type VariantProps } from "class-variance-authority"
import type { AppIcon } from "@/lib/icons"
import { Icon as AppIconGlyph, type IconSize } from "@/components/ui/icon"

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
  sm: "sm",
  md: "md",
  lg: "md",
  xl: "lg",
} as const satisfies Record<NonNullable<VariantProps<typeof iconBoxVariants>["size"]>, IconSize>

export interface IconBoxProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof iconBoxVariants> {
  icon: AppIcon
  iconClassName?: string
}

export function IconBox({
  className,
  size = "sm",
  variant,
  icon,
  iconClassName,
  ...props
}: IconBoxProps) {
  return (
    <div className={cn(iconBoxVariants({ size, variant }), className)} {...props}>
      <AppIconGlyph
        icon={icon}
        size={iconSizeMap[size ?? "sm"]}
        className={cn("text-foreground/70", iconClassName)}
      />
    </div>
  )
}
