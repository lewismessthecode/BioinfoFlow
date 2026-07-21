import { cn } from "@/lib/utils"
import { cva, type VariantProps } from "class-variance-authority"

const statusBadgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium transition-colors",
  {
    variants: {
      variant: {
        success: "bg-success-muted text-success-foreground border-success-border",
        warning: "bg-warning-muted text-warning border-warning-border",
        info: "bg-info-muted text-info border-info-border",
        neutral: "bg-muted text-muted-foreground border-border",
        destructive: "bg-error-muted text-error-foreground border-error-border",
        running: "bg-warning-muted text-warning border-warning-border animate-subtle-pulse motion-reduce:animate-none",
      },
    },
    defaultVariants: {
      variant: "neutral",
    },
  }
)

export interface StatusBadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof statusBadgeVariants> {
  children: React.ReactNode
}

export function StatusBadge({ className, variant, children, ...props }: StatusBadgeProps) {
  return (
    <div className={cn(statusBadgeVariants({ variant }), className)} {...props}>
      {children}
    </div>
  )
}
