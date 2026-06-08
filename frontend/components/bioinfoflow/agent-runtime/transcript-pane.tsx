"use client"

import { TurnStream } from "./turn-stream"
import type { AgentRuntimeTurn } from "@/lib/agent-runtime"

export function TranscriptPane({ turns }: { turns: AgentRuntimeTurn[] }) {
  return (
    <div className="min-h-0 flex-1 overflow-y-auto px-4 sm:px-6">
      <TurnStream turns={turns} />
    </div>
  )
}
