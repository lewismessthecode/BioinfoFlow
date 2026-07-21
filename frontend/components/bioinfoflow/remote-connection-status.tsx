import type { RemoteConnectionStatus } from "@/lib/demo-connections"
import { cn } from "@/lib/utils"

const remoteConnectionStatusDotClassNames: Record<RemoteConnectionStatus, string> = {
  online: "bg-success ring-success-muted",
  offline: "bg-error ring-error-muted",
  error: "bg-error ring-error-muted",
  unknown: "bg-muted-foreground/60 ring-muted",
}

export function RemoteConnectionStatusDot({
  status,
  className,
}: {
  status: RemoteConnectionStatus
  className?: string
}) {
  return (
    <span
      className={cn(
        "h-2.5 w-2.5 rounded-full ring-4",
        remoteConnectionStatusDotClassNames[status],
        className,
      )}
      aria-hidden="true"
    />
  )
}
