"use client"

import { AgentActivityGroup, AgentToolCard } from "@/components/bioinfoflow/agent/agent-activity"
import { AgentMessagePart } from "@/components/bioinfoflow/agent/message-part-registry"
import type {
  MessagePart,
  ToolCallPart,
  ToolProgressView,
  ToolResultPart,
} from "@/lib/agent/contracts"

type AgentMessagePartsProps = {
  parts: MessagePart[]
  toolResultsByCallId?: ReadonlyMap<string, ToolResultPart>
  liveToolsByCallId?: ReadonlyMap<string, ToolProgressView>
  onOpenRun?: (runId: string) => void
}

type MessageRenderBlock =
  | { kind: "part"; part: Exclude<MessagePart, ToolCallPart> }
  | { kind: "tool_calls"; key: string; calls: ToolCallPart[] }

const EMPTY_TOOL_RESULTS = new Map<string, ToolResultPart>()
const EMPTY_LIVE_TOOLS = new Map<string, ToolProgressView>()

export function AgentMessageParts({
  parts,
  toolResultsByCallId = EMPTY_TOOL_RESULTS,
  liveToolsByCallId = EMPTY_LIVE_TOOLS,
  onOpenRun,
}: AgentMessagePartsProps) {
  const blocks = groupContiguousToolCalls(parts)
  const messageToolCallIds = new Set(
    parts.flatMap((part) => (part.type === "tool_call" ? [part.call_id] : [])),
  )

  return (
    <div className="grid min-w-0 gap-3">
      {blocks.map((block) => {
        if (block.kind === "tool_calls") {
          const tools = block.calls.map((call) =>
            toolProgressFromParts(
              call,
              toolResultsByCallId.get(call.call_id),
              liveToolsByCallId.get(call.call_id),
            ),
          )
          const results = block.calls.flatMap((call) => {
            const result = toolResultsByCallId.get(call.call_id)
            return result ? [result] : []
          })

          return (
            <div key={block.key} className="grid min-w-0 gap-2">
              {tools.length === 1 ? (
                <AgentToolCard tool={tools[0]} />
              ) : (
                <AgentActivityGroup tools={tools} />
              )}
              <ToolOutputContentParts results={results} onOpenRun={onOpenRun} />
            </div>
          )
        }

        const part = block.part
        if (part.type === "tool_result" && messageToolCallIds.has(part.call_id)) {
          return null
        }
        return (
          <AgentMessagePart
            key={part.id}
            part={part}
            onOpenRun={onOpenRun}
            nestedContent={
              part.type === "tool_result" ? (
                <ToolOutputContentParts results={[part]} onOpenRun={onOpenRun} />
              ) : undefined
            }
          />
        )
      })}
    </div>
  )
}

function ToolOutputContentParts({
  results,
  onOpenRun,
}: {
  results: ToolResultPart[]
  onOpenRun?: (runId: string) => void
}) {
  const outputParts = results.flatMap((result) =>
    result.output?.type === "content_parts" ? result.output.parts : [],
  )
  if (outputParts.length === 0) return null

  return (
    <div className="ml-3 border-l border-border/60 pl-3">
      <AgentMessageParts parts={outputParts} onOpenRun={onOpenRun} />
    </div>
  )
}

function toolProgressFromParts(
  call: ToolCallPart,
  result?: ToolResultPart,
  live?: ToolProgressView,
): ToolProgressView {
  const durable: ToolProgressView = {
    call_id: call.call_id,
    group_id: call.group_id,
    execution_mode: call.execution_mode,
    name: call.name,
    display_name: call.display_name,
    category: call.category,
    summary: call.summary,
    arguments: {},
    status: result?.status ?? "pending",
    revision: 0,
    started_at: result?.started_at ?? null,
    completed_at: result?.completed_at ?? null,
    input_summary: null,
    output_summary: result?.summary ?? null,
    error: result?.error ?? null,
    public_details: [
      ...(call.public_details ?? []),
      ...(result?.public_details ?? []),
    ],
  }

  if (!live) return durable

  return {
    ...durable,
    status: live.status,
    revision: live.revision,
    started_at: live.started_at ?? durable.started_at,
    completed_at: live.completed_at ?? durable.completed_at,
    input_summary: live.input_summary,
    output_summary: live.output_summary ?? durable.output_summary,
    error: live.error ?? durable.error,
    public_details: live.public_details ?? durable.public_details,
  }
}

function groupContiguousToolCalls(parts: MessagePart[]): MessageRenderBlock[] {
  const blocks: MessageRenderBlock[] = []

  for (let index = 0; index < parts.length; index += 1) {
    const part = parts[index]
    if (part.type !== "tool_call") {
      blocks.push({ kind: "part", part })
      continue
    }

    const calls = [part]
    let nextPart = parts[index + 1]
    while (
      nextPart?.type === "tool_call" &&
      nextPart.group_id === part.group_id
    ) {
      index += 1
      calls.push(nextPart)
      nextPart = parts[index + 1]
    }
    blocks.push({
      kind: "tool_calls",
      key: `${part.group_id}:${part.id}`,
      calls,
    })
  }

  return blocks
}
