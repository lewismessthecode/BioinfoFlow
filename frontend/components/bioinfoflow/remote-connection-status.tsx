import type { RemoteConnectionStatus } from "@/lib/demo-connections"
import { cn } from "@/lib/utils"

const remoteConnectionStatusDotClassNames: Record<RemoteConnectionStatus, string> = {
  online: "bg-emerald-500 shadow-emerald-500/40",
  offline: "bg-rose-500 shadow-rose-500/40",
  error: "bg-rose-500 shadow-rose-500/40",
  unknown: "bg-slate-400 shadow-slate-400/30",
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
        "h-2.5 w-2.5 rounded-full shadow-[0_0_0_4px]",
        remoteConnectionStatusDotClassNames[status],
        className,
      )}
      aria-hidden="true"
    />
  )
}
