"use client"

import { memo, useState, useCallback } from "react"
import { ShieldAlert, Check, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import type { ApprovalPart as ApprovalPartType } from "@/lib/chat-types"

interface ApprovalPartProps {
  part: ApprovalPartType
  onResolve: (approvalId: string, action: "approve" | "reject") => void
}

function formatToolArgs(args: Record<string, unknown>): string {
  const entries = Object.entries(args)
  if (entries.length === 0) return ""
  return entries
    .slice(0, 3)
    .map(([key, value]) => {
      const strValue = typeof value === "string" ? value : JSON.stringify(value)
      const truncated = strValue.length > 60 ? `${strValue.slice(0, 60)}...` : strValue
      return `${key}: ${truncated}`
    })
    .join("\n")
}

export const ApprovalPart = memo(function ApprovalPart({
  part,
  onResolve,
}: ApprovalPartProps) {
  const [resolving, setResolving] = useState(false)

  const handleResolve = useCallback(
    async (action: "approve" | "reject") => {
      setResolving(true)
      try {
        await onResolve(part.approvalId, action)
      } catch {
        setResolving(false)
      }
    },
    [onResolve, part.approvalId],
  )

  // Reset resolving when parent updates status
  const effectiveResolving = resolving && part.status === "pending"

  const isPending = part.status === "pending"
  const isApproved = part.status === "approved"
  const isRejected = part.status === "rejected"
  const isCancelled = part.status === "cancelled"

  return (
    <div
      role={isPending ? "alert" : undefined}
      className={cn(
        "rounded-lg border p-3 my-2 transition-colors duration-300",
        isPending && "border-amber-500/40 bg-amber-500/5",
        isApproved && "border-emerald-500/30 bg-emerald-500/5",
        isRejected && "border-destructive/30 bg-destructive/5",
        isCancelled && "border-border bg-muted/20 opacity-60",
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <ShieldAlert
          className={cn(
            "h-4 w-4 shrink-0",
            isPending && "text-amber-500",
            isApproved && "text-emerald-500",
            isRejected && "text-destructive",
            isCancelled && "text-muted-foreground",
          )}
        />
        <span className="text-sm font-medium text-foreground">
          Approval required
        </span>
        {isPending && (
          <span className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground">
            <span
              className="inline-block h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse"
              aria-hidden
            />
            Awaiting approval
          </span>
        )}
        {isApproved && (
          <span className="ml-auto flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
            <Check className="h-3 w-3" />
            Approved
          </span>
        )}
        {isRejected && (
          <span className="ml-auto flex items-center gap-1 text-xs text-destructive">
            <X className="h-3 w-3" />
            Rejected
          </span>
        )}
        {isCancelled && (
          <span className="ml-auto text-xs text-muted-foreground">
            Cancelled
          </span>
        )}
      </div>

      {/* Tool info */}
      <div className="ml-6 space-y-1">
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-muted-foreground">
            {part.toolName}
          </span>
          <span className="text-[10px] rounded border px-1 py-0.5 text-muted-foreground/70 uppercase tracking-wider">
            {part.approvalType}
          </span>
        </div>
        {Object.keys(part.toolInput).length > 0 && (
          <pre className="text-xs text-muted-foreground/80 font-mono whitespace-pre-wrap break-all leading-relaxed max-h-[80px] overflow-y-auto">
            {formatToolArgs(part.toolInput)}
          </pre>
        )}
      </div>

      {/* Action buttons */}
      {isPending && !effectiveResolving && (
        <div className="flex items-center gap-2 mt-3 ml-6">
          <Button
            size="sm"
            variant="outline"
            className={cn(
              "h-8 px-4 text-xs font-medium",
              "border-emerald-600/60 bg-emerald-600 text-white",
              "hover:bg-emerald-700 hover:border-emerald-700 hover:text-white",
              "dark:border-emerald-500/60 dark:bg-emerald-600 dark:text-white",
              "dark:hover:bg-emerald-700",
            )}
            onClick={() => handleResolve("approve")}
          >
            <Check className="h-3.5 w-3.5 mr-1.5" />
            Approve
          </Button>
          <Button
            size="sm"
            variant="outline"
            className={cn(
              "h-8 px-4 text-xs font-medium",
              "border-destructive/40 text-destructive",
              "hover:bg-destructive/10 hover:text-destructive",
            )}
            onClick={() => handleResolve("reject")}
          >
            <X className="h-3.5 w-3.5 mr-1.5" />
            Deny
          </Button>
        </div>
      )}
      {effectiveResolving && (
        <div className="mt-3 ml-6 text-xs text-muted-foreground animate-pulse">
          Resolving...
        </div>
      )}
    </div>
  )
})
