"use client"

import { useTranslations } from "next-intl"

import { AgentActivityGroup, AgentToolCard } from "@/components/bioinfoflow/agent/agent-activity"
import { AgentArtifactReference } from "@/components/bioinfoflow/agent/agent-artifact"
import { AgentThinking } from "@/components/bioinfoflow/agent/agent-thinking"
import { MarkdownRenderer } from "@/components/bioinfoflow/markdown-renderer"
import { Badge } from "@/components/ui/badge"
import type {
  AttachmentRefPart,
  DirectoryRefPart,
  FileRefPart,
  MessagePart,
  RunRefPart,
  ToolCallPart,
  ToolProgressView,
  ToolResultPart,
  WorkflowRefPart,
} from "@/lib/agent/contracts"

type AgentMessagePartsProps = {
  parts: MessagePart[]
  toolResultsByCallId?: ReadonlyMap<string, ToolResultPart>
  liveToolsByCallId?: ReadonlyMap<string, ToolProgressView>
}

type ReferencePart =
  | AttachmentRefPart
  | FileRefPart
  | DirectoryRefPart
  | WorkflowRefPart
  | RunRefPart

type MessageRenderBlock =
  | { kind: "part"; part: Exclude<MessagePart, ToolCallPart> }
  | { kind: "tool_calls"; key: string; calls: ToolCallPart[] }

const EMPTY_TOOL_RESULTS = new Map<string, ToolResultPart>()
const EMPTY_LIVE_TOOLS = new Map<string, ToolProgressView>()

export function AgentMessageParts({
  parts,
  toolResultsByCallId = EMPTY_TOOL_RESULTS,
  liveToolsByCallId = EMPTY_LIVE_TOOLS,
}: AgentMessagePartsProps) {
  const t = useTranslations("agentHistory")
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
              <ToolOutputContentParts results={results} />
            </div>
          )
        }

        const part = block.part
        if (part.type === "text") {
          return <MarkdownRenderer key={part.id} content={part.text} />
        }

        if (part.type === "reasoning_summary") {
          return (
            <AgentThinking
              key={part.id}
              label={t("reasoning.title")}
              part={part}
            />
          )
        }

        if (part.type === "tool_result") {
          if (messageToolCallIds.has(part.call_id)) return null
          return <UnpairedToolResult key={part.id} result={part} />
        }

        if (part.type === "artifact_ref") {
          return <AgentArtifactReference key={part.id} part={part} />
        }

        if (isReferencePart(part)) {
          return <ReferenceRow key={part.id} part={part} />
        }

        return (
          <div
            key={part.id}
            className="grid gap-1 rounded-[10px] border border-border/60 bg-muted/25 px-3 py-2"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-medium text-foreground/80">
                {t("unknown.title")}
              </span>
              <Badge
                variant="outline"
                className="font-mono text-[10px]"
                translate="no"
              >
                {part.original_type}
              </Badge>
            </div>
            <p className="text-xs leading-5 text-muted-foreground">
              {part.display_text}
            </p>
          </div>
        )
      })}
    </div>
  )
}

function ReferenceRow({ part }: { part: ReferencePart }) {
  const t = useTranslations("agentHistory")
  const reference = referenceView(part)

  return (
    <div className="flex min-w-0 items-center gap-2 rounded-[8px] border border-border/60 bg-background px-2.5 py-2 text-xs">
      <Badge variant="outline">{t(`reference.${reference.kind}`)}</Badge>
      <span className="min-w-0 flex-1 truncate font-medium text-foreground/80">
        {reference.label}
      </span>
      {reference.detail ? (
        <span
          className="max-w-[50%] truncate font-mono text-[11px] text-muted-foreground"
          translate="no"
        >
          {reference.detail}
        </span>
      ) : null}
    </div>
  )
}

function UnpairedToolResult({ result }: { result: ToolResultPart }) {
  const t = useTranslations("agentActivity")
  const publicContent =
    result.summary ?? result.error

  return (
    <div className="grid min-w-0 gap-2">
      <div className="flex min-w-0 items-start gap-2 rounded-[8px] border border-border/60 bg-muted/20 px-3 py-2 text-xs">
        <Badge variant="outline">{t(`status.${result.status}`)}</Badge>
        {publicContent ? (
          <p className="min-w-0 flex-1 whitespace-pre-wrap break-words leading-5 text-foreground/75">
            {publicContent}
          </p>
        ) : null}
      </div>
      <ToolOutputContentParts results={[result]} />
    </div>
  )
}

function ToolOutputContentParts({ results }: { results: ToolResultPart[] }) {
  const outputParts = results.flatMap((result) =>
    result.output?.type === "content_parts" ? result.output.parts : [],
  )
  if (outputParts.length === 0) return null

  return (
    <div className="ml-3 border-l border-border/60 pl-3">
      <AgentMessageParts parts={outputParts} />
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

function isReferencePart(part: MessagePart): part is ReferencePart {
  return [
    "attachment_ref",
    "file_ref",
    "directory_ref",
    "workflow_ref",
    "run_ref",
  ].includes(part.type)
}

function referenceView(part: ReferencePart) {
  if (part.type === "attachment_ref") {
    return {
      kind: "attachment" as const,
      label: part.filename,
      detail: part.mime_type,
    }
  }
  if (part.type === "file_ref") {
    return { kind: "file" as const, label: part.label, detail: part.path }
  }
  if (part.type === "directory_ref") {
    return { kind: "directory" as const, label: part.label, detail: part.path }
  }
  if (part.type === "workflow_ref") {
    return {
      kind: "workflow" as const,
      label: part.label,
      detail: part.workflow_id,
    }
  }
  return { kind: "run" as const, label: part.label, detail: part.run_id }
}
