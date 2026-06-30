import { RemoteConnectionStatusDot } from "@/components/bioinfoflow/remote-connection-status"
import type { RemoteConnectionStatus } from "@/lib/demo-connections"

export const statusBorderClassNames: Record<RemoteConnectionStatus, string> = {
  online: "border-emerald-500/20 bg-emerald-500/5 text-emerald-700 dark:text-emerald-300",
  offline: "border-rose-500/20 bg-rose-500/5 text-rose-700 dark:text-rose-300",
  error: "border-amber-500/20 bg-amber-500/5 text-amber-700 dark:text-amber-300",
  unknown: "border-slate-500/20 bg-slate-500/5 text-slate-700 dark:text-slate-300",
}

export function StatusDot({
  status,
  className,
}: {
  status: RemoteConnectionStatus
  className?: string
}) {
  return <RemoteConnectionStatusDot status={status} className={className} />
}

export function TextPanel({ title, value, empty }: { title: string; value: string; empty: string }) {
  return (
    <div className="rounded-xl border border-border/40 bg-muted/20 p-3">
      <p className="text-xs font-medium text-muted-foreground">{title}</p>
      <pre className="mt-2 max-h-28 overflow-y-auto whitespace-pre-wrap break-words font-sans text-xs leading-5 text-foreground [scrollbar-gutter:stable]">
        {value || empty}
      </pre>
    </div>
  )
}
