import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import type { AppIcon } from "@/lib/icons"
import { Icon as AppIconGlyph } from "@/components/ui/icon"

export interface EmptyStateProps {
  icon: AppIcon
  title: string
  description: string
  action?: {
    label: string
    onClick: () => void
  }
  className?: string
}

export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn("flex flex-col items-center justify-center py-12 px-4 text-center", className)}>
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-xl bg-muted/30">
        <AppIconGlyph icon={icon} size="xl" className="text-muted-foreground" />
      </div>
      <h2 className="mb-2 text-lg font-medium text-foreground">{title}</h2>
      <p className="text-sm text-muted-foreground max-w-md mb-6">{description}</p>
      {action && (
        <Button onClick={action.onClick} variant="default">
          {action.label}
        </Button>
      )}
    </div>
  )
}
