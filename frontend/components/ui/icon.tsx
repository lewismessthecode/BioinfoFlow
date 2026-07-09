import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import type { AppIcon } from "@/lib/icons"
import { cn } from "@/lib/utils"

export const iconSizes = {
  xs: "size-3",
  sm: "size-3.5",
  md: "size-4",
  lg: "size-5",
  xl: "size-6",
} as const

export const iconStrokeWidth = 1.75

export type IconSize = keyof typeof iconSizes

export interface IconProps extends React.SVGAttributes<SVGSVGElement> {
  icon: AppIcon
  size?: IconSize
  decorative?: boolean
}

export function Icon({
  icon: Glyph,
  size = "md",
  decorative = true,
  className,
  strokeWidth = iconStrokeWidth,
  ...props
}: IconProps) {
  return (
    <Glyph
      aria-hidden={decorative ? "true" : undefined}
      className={cn("shrink-0", iconSizes[size], className)}
      strokeWidth={strokeWidth}
      {...props}
    />
  )
}

const iconButtonVariants = cva(
  "inline-flex shrink-0 items-center justify-center rounded-md text-muted-foreground transition-[background-color,border-color,box-shadow,color,transform] duration-150 ease-out hover:bg-accent hover:text-accent-foreground active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] outline-none",
  {
    variants: {
      size: {
        sm: "size-8",
        md: "size-9",
        lg: "size-10",
      },
      tone: {
        default: "",
        sidebar:
          "text-sidebar-foreground/68 hover:bg-sidebar-foreground/[0.055] hover:text-sidebar-foreground focus-visible:bg-sidebar-foreground/[0.06]",
        subtle: "text-foreground/62 hover:bg-foreground/[0.055] hover:text-foreground",
        destructive:
          "text-destructive hover:bg-destructive/10 hover:text-destructive",
      },
    },
    defaultVariants: {
      size: "md",
      tone: "default",
    },
  },
)

const iconButtonIconSize: Record<NonNullable<VariantProps<typeof iconButtonVariants>["size"]>, IconSize> = {
  sm: "sm",
  md: "md",
  lg: "md",
}

export interface IconButtonProps
  extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "children">,
    VariantProps<typeof iconButtonVariants> {
  icon: AppIcon
  label: string
  iconClassName?: string
}

export function IconButton({
  icon,
  label,
  size = "md",
  tone,
  className,
  iconClassName,
  type = "button",
  ...props
}: IconButtonProps) {
  return (
    <button
      type={type}
      aria-label={label}
      className={cn(iconButtonVariants({ size, tone }), className)}
      {...props}
    >
      <Icon
        icon={icon}
        size={iconButtonIconSize[size ?? "md"]}
        className={iconClassName}
      />
    </button>
  )
}

const iconSurfaceVariants = cva(
  "inline-flex shrink-0 items-center justify-center rounded-md border border-border/60 bg-secondary/50 text-muted-foreground transition-colors duration-150 dark:bg-secondary/30",
  {
    variants: {
      size: {
        sm: "size-8",
        md: "size-9",
        lg: "size-10",
        xl: "size-12",
      },
      tone: {
        default: "",
        muted: "border-transparent bg-muted/30",
        primary: "border-transparent bg-primary/10 text-primary",
        surface: "border-transparent bg-secondary",
      },
    },
    defaultVariants: {
      size: "sm",
      tone: "default",
    },
  },
)

const iconSurfaceIconSize: Record<NonNullable<VariantProps<typeof iconSurfaceVariants>["size"]>, IconSize> = {
  sm: "sm",
  md: "md",
  lg: "md",
  xl: "lg",
}

export interface IconSurfaceProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof iconSurfaceVariants> {
  icon: AppIcon
  iconClassName?: string
}

export function IconSurface({
  icon,
  size = "sm",
  tone,
  className,
  iconClassName,
  ...props
}: IconSurfaceProps) {
  return (
    <span className={cn(iconSurfaceVariants({ size, tone }), className)} {...props}>
      <Icon
        icon={icon}
        size={iconSurfaceIconSize[size ?? "sm"]}
        className={iconClassName}
      />
    </span>
  )
}
