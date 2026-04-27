"use client"

import { memo, useState, useEffect, useRef } from "react"
import { ChevronDown } from "lucide-react"
import { MarkdownRenderer } from "@/components/bioinfoflow/markdown-renderer"
import { cn } from "@/lib/utils"
import type { ThinkingPart as ThinkingPartType } from "@/lib/chat-types"

interface ThinkingPartProps {
  part: ThinkingPartType
}

export const ThinkingPart = memo(function ThinkingPart({ part }: ThinkingPartProps) {
  const [expanded, setExpanded] = useState(false)
  const startRef = useRef<number | null>(null)
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    if (startRef.current == null) {
      startRef.current = Date.now()
    }
    if (!part.isStreaming) return
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - (startRef.current ?? Date.now())) / 1000))
    }, 1000)
    return () => clearInterval(interval)
  }, [part.isStreaming])

  const label = part.isStreaming
    ? "Thinking..."
    : `Thought for ${elapsed < 1 ? "<1" : elapsed}s`

  return (
    <div className="rounded-lg border border-border/50 bg-muted/30">
      <button
        type="button"
        className="flex w-full items-center justify-between px-3 py-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <span>{label}</span>
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 transition-transform duration-200",
            expanded && "rotate-180"
          )}
        />
      </button>
      {expanded && (
        <div className="border-t border-border/50 px-3 py-2">
          <MarkdownRenderer
            content={part.text}
            className="
              text-xs
              text-muted-foreground
              [&_code]:text-[0.95em]
              [&_li]:text-xs
              [&_li]:leading-relaxed
              [&_ol]:my-2
              [&_p]:mb-2
              [&_p]:text-xs
              [&_p]:leading-relaxed
              [&_pre]:my-2
              [&_strong]:text-foreground
              [&_ul]:my-2
            "
          />
        </div>
      )}
    </div>
  )
})
