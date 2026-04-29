"use client"

import { memo, useState } from "react"
import { Loader2, CheckCircle2, XCircle, ChevronRight, Wrench, CircleSlash } from "lucide-react"
import { cn } from "@/lib/utils"
import type { ToolCallPart as ToolCallPartType } from "@/lib/chat-types"

interface ToolCallPartProps {
  part: ToolCallPartType
}

interface ToolCallGroupProps {
  parts: ToolCallPartType[]
  isActiveFallback?: boolean
}

const statusIcon = {
  running: { icon: Loader2, className: "animate-spin text-primary" },
  done: { icon: CheckCircle2, className: "text-emerald-500" },
  error: { icon: XCircle, className: "text-destructive" },
  cancelled: { icon: CircleSlash, className: "text-muted-foreground" },
} as const

/** Truncate text to a max length, adding ellipsis */
function truncateResult(text: string, maxLines: number): string {
  const lines = text.split("\n")
  if (lines.length <= maxLines) return text
  return lines.slice(0, maxLines).join("\n") + "\n..."
}

/** Format a tool result as a brief inline preview */
function ToolResultPreview({ part }: { part: ToolCallPartType }) {
  if (part.status === "running" && part.progressText) {
    return (
      <div className="mt-1.5 text-[11px] text-muted-foreground/80">
        {part.progressText}
      </div>
    )
  }

  if (!part.result || part.status === "running") return null

  const result = part.result
  const toolName = part.toolName
  const structured = part.resultData

  // For error results, show as-is
  if (part.status === "error") {
    return (
      <pre className="mt-1.5 text-[11px] leading-relaxed text-destructive/80 font-mono whitespace-pre-wrap break-all max-h-[80px] overflow-y-auto">
        {truncateResult(result, 5)}
      </pre>
    )
  }

  // Tools known to return JSON — parse only for these
  const jsonTools = new Set(["file_read", "grep", "execute_code", "web_search", "pubmed_search", "chembl_search"])
  let parsed: unknown = structured ?? null
  if (parsed === null && jsonTools.has(toolName)) {
    try {
      parsed = JSON.parse(result)
    } catch {
      // Not valid JSON — fall through to raw display
    }
  }

  if (typeof parsed === "object" && parsed !== null) {
    const summary = (parsed as Record<string, unknown>).summary
    if (typeof summary === "string" && summary.trim()) {
      return (
        <div className="mt-1.5 text-[11px] text-muted-foreground/80">
          {summary}
        </div>
      )
    }
  }

  // file_read: show content snippet
  if (toolName === "file_read" && typeof parsed === "object" && parsed !== null) {
    const content = (parsed as Record<string, unknown>).content
    if (typeof content === "string") {
      return (
        <pre className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground/80 font-mono whitespace-pre-wrap break-all max-h-[100px] overflow-y-auto rounded bg-secondary/40 px-2 py-1.5">
          {truncateResult(content, 8)}
        </pre>
      )
    }
  }

  // grep: show match count and first few results
  if (toolName === "grep" && typeof parsed === "object" && parsed !== null) {
    const matches = (parsed as Record<string, unknown>).matches
    if (Array.isArray(matches)) {
      return (
        <div className="mt-1.5 text-[11px] text-muted-foreground/80">
          <span className="font-medium">{matches.length} matches</span>
          {matches.length > 0 && (
            <pre className="mt-1 font-mono whitespace-pre-wrap break-all max-h-[80px] overflow-y-auto rounded bg-secondary/40 px-2 py-1">
              {matches.slice(0, 3).map((m: unknown) =>
                typeof m === "string" ? m : JSON.stringify(m)
              ).join("\n")}
              {matches.length > 3 && `\n... +${matches.length - 3} more`}
            </pre>
          )}
        </div>
      )
    }
  }

  // execute_code: structured output with stdout/stderr/return_value
  if (toolName === "execute_code" && typeof parsed === "object" && parsed !== null) {
    const obj = parsed as Record<string, unknown>
    const stdout = typeof obj.stdout === "string" ? obj.stdout : ""
    const stderr = typeof obj.stderr === "string" ? obj.stderr : ""
    const returnValue = obj.return_value !== undefined ? String(obj.return_value) : ""

    if (stdout || stderr || returnValue) {
      return (
        <div className="mt-1.5 space-y-1">
          {stdout && (
            <pre className="text-[11px] leading-relaxed text-emerald-600 dark:text-emerald-400 font-mono whitespace-pre-wrap break-all max-h-[100px] overflow-y-auto rounded bg-secondary/40 px-2 py-1.5">
              {truncateResult(stdout, 8)}
            </pre>
          )}
          {stderr && (
            <pre className="text-[11px] leading-relaxed text-destructive/80 font-mono whitespace-pre-wrap break-all max-h-[60px] overflow-y-auto rounded bg-destructive/5 px-2 py-1.5">
              {truncateResult(stderr, 4)}
            </pre>
          )}
          {returnValue && !stdout && (
            <pre className="text-[11px] leading-relaxed text-muted-foreground/80 font-mono whitespace-pre-wrap break-all max-h-[60px] overflow-y-auto rounded bg-secondary/40 px-2 py-1.5">
              → {truncateResult(returnValue, 3)}
            </pre>
          )}
        </div>
      )
    }
  }

  // shell: show command output
  if (toolName === "shell" && typeof result === "string") {
    return (
      <pre className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground/80 font-mono whitespace-pre-wrap break-all max-h-[100px] overflow-y-auto rounded bg-secondary/40 px-2 py-1.5">
        {truncateResult(result, 8)}
      </pre>
    )
  }

  // web_search / pubmed_search: show result titles
  if ((toolName === "web_search" || toolName === "pubmed_search") && typeof parsed === "object" && parsed !== null) {
    const results = (parsed as Record<string, unknown>).results
    if (Array.isArray(results)) {
      return (
        <div className="mt-1.5 space-y-0.5">
          {results.slice(0, 3).map((r: unknown, i: number) => {
            const item = r as Record<string, unknown>
            const title = (item.title as string) || (item.name as string) || ""
            return (
              <div key={i} className="text-[11px] text-muted-foreground/80 truncate">
                &bull; {title}
              </div>
            )
          })}
          {results.length > 3 && (
            <div className="text-[11px] text-muted-foreground/60">
              +{results.length - 3} more
            </div>
          )}
        </div>
      )
    }
  }

  // Default: truncated raw text
  if (result.length > 0) {
    return (
      <pre className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground/70 font-mono whitespace-pre-wrap break-all max-h-[80px] overflow-y-auto">
        {truncateResult(result, 5)}
      </pre>
    )
  }

  return null
}

function SingleToolCall({ part, showPreview }: { part: ToolCallPartType; showPreview?: boolean }) {
  const config = statusIcon[part.status]
  const Icon = config.icon
  return (
    <div className="py-1">
      <div className="flex items-start gap-2 text-xs">
        <Icon className={cn("mt-0.5 h-3 w-3 shrink-0", config.className)} />
        <span className="font-mono text-muted-foreground">{part.toolName}</span>
        {part.status === "running" && part.progressText && (
          <span className="truncate text-muted-foreground/70">{part.progressText}</span>
        )}
        {part.durationMs != null && part.status !== "running" && (
          <span className="ml-auto text-muted-foreground/60 tabular-nums">
            {part.durationMs < 1000
              ? `${Math.round(part.durationMs)}ms`
              : `${(part.durationMs / 1000).toFixed(1)}s`}
          </span>
        )}
      </div>
      {showPreview && <ToolResultPreview part={part} />}
    </div>
  )
}

/** Collapsible group that uses a lightweight disclosure row. */
export const ToolCallGroup = memo(function ToolCallGroup({ parts, isActiveFallback = false }: ToolCallGroupProps) {
  const [expanded, setExpanded] = useState(false)

  const hasError = parts.some((p) => p.status === "error")
  const isRunning = parts.some((p) => p.status === "running")
  const isActive = isRunning || (isActiveFallback && !hasError)

  const label = isRunning
    ? `Running tools (${parts.filter((p) => p.status === "done").length}/${parts.length})`
    : isActive
      ? "Working with tools..."
    : hasError
      ? `Used ${parts.length} tools (${parts.filter((p) => p.status === "error").length} failed)`
      : `Used ${parts.length} tools`

  const totalMs = parts.reduce((sum, p) => sum + (p.durationMs ?? 0), 0)

  return (
    <div className="space-y-1">
      <button
        type="button"
        aria-expanded={expanded}
        className="flex w-full items-center gap-2 px-1 py-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
        onClick={() => setExpanded(!expanded)}
      >
        <ChevronRight
          className={cn(
            "h-3.5 w-3.5 shrink-0 transition-transform duration-200",
            expanded && "rotate-90"
          )}
        />
        {isActive ? (
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
        ) : (
          <Wrench className="h-3.5 w-3.5 shrink-0 text-muted-foreground/70" />
        )}
        <span>{label}</span>
        {!isActive && totalMs > 0 && (
          <span className="ml-auto text-muted-foreground/60 tabular-nums">
            {totalMs < 1000 ? `${Math.round(totalMs)}ms` : `${(totalMs / 1000).toFixed(1)}s`}
          </span>
        )}
      </button>
      {expanded && (
        <div className="ml-5 space-y-1">
          {parts.map((part) => (
            <SingleToolCall key={part.id} part={part} showPreview />
          ))}
        </div>
      )}
    </div>
  )
})

/** Standalone single tool call — still exported for backward compat. */
export const ToolCallPart = memo(function ToolCallPart({ part }: ToolCallPartProps) {
  const config = statusIcon[part.status]
  const Icon = config.icon

  return (
    <div className="px-1 py-1 text-xs text-muted-foreground">
      <div className="flex items-start gap-2">
        <Icon className={cn("mt-0.5 h-3.5 w-3.5 shrink-0", config.className)} />
        <div className="min-w-0 flex-1">
          <span className="block truncate font-mono text-foreground/85">
            {part.toolName}
          </span>
          {part.status === "running" && part.progressText && (
            <span className="block text-[11px] text-muted-foreground/70">
              {part.progressText}
            </span>
          )}
          {part.durationMs != null && part.status !== "running" && (
            <span className="text-xs text-muted-foreground/60 tabular-nums">
              {part.durationMs < 1000
                ? `${Math.round(part.durationMs)}ms`
                : `${(part.durationMs / 1000).toFixed(1)}s`}
            </span>
          )}
          <ToolResultPreview part={part} />
        </div>
      </div>
    </div>
  )
})
