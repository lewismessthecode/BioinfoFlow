"use client"

import type { AgentStarterPrompt } from "@/lib/agent/bootstrap"
import { CheckCircle2, FileText, MessageSquare, Search } from "@/lib/icons"

const icons = {
  check: CheckCircle2,
  explain: FileText,
  review: Search,
  chat: MessageSquare,
} satisfies Record<AgentStarterPrompt["icon"], typeof CheckCircle2>

export function AgentStarterPrompts({
  prompts,
  onSelect,
}: {
  prompts: AgentStarterPrompt[]
  onSelect: (prompt: AgentStarterPrompt) => void
}) {
  if (prompts.length === 0) return null
  return (
    <div className="mx-auto grid w-full max-w-[42rem] gap-1 px-4" aria-label="Starter prompts">
      {prompts.map((prompt) => {
        const Icon = icons[prompt.icon]
        return (
          <button
            key={prompt.id}
            type="button"
            className="group flex min-h-11 w-full items-center gap-3 rounded-xl px-3 py-2 text-left text-sm text-foreground/78 transition-colors hover:bg-agent-activity-hover hover:text-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/45 motion-reduce:transition-none"
            onClick={() => onSelect(prompt)}
          >
            <Icon aria-hidden="true" className="size-4 text-muted-foreground transition-colors group-hover:text-foreground/70" />
            <span className="truncate">{prompt.title}</span>
          </button>
        )
      })}
    </div>
  )
}
