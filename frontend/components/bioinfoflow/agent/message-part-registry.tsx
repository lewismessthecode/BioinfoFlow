"use client"

import type { ReactNode } from "react"
import { useTranslations } from "next-intl"

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
  WorkflowRefPart,
} from "@/lib/agent/contracts"
import { ChevronRight } from "@/lib/icons"

type RenderablePart = Exclude<MessagePart, ToolCallPart>
type ReferencePart =
  | AttachmentRefPart
  | FileRefPart
  | DirectoryRefPart
  | WorkflowRefPart
  | RunRefPart

type MessagePartRendererProps = {
  part: RenderablePart
  onOpenRun?: (runId: string) => void
  nestedContent?: ReactNode
}

type PartRenderer = (props: MessagePartRendererProps) => ReactNode

const MESSAGE_PART_RENDERERS = {
  text: TextPartRenderer,
  reasoning_summary: ReasoningPartRenderer,
  tool_result: ToolResultRenderer,
  artifact_ref: ArtifactPartRenderer,
  attachment_ref: ReferencePartRenderer,
  file_ref: ReferencePartRenderer,
  directory_ref: ReferencePartRenderer,
  workflow_ref: ReferencePartRenderer,
  run_ref: ReferencePartRenderer,
  unknown: UnknownPartRenderer,
} satisfies Record<RenderablePart["type"], PartRenderer>

export function AgentMessagePart(props: MessagePartRendererProps) {
  return MESSAGE_PART_RENDERERS[props.part.type](props)
}

function TextPartRenderer({ part }: MessagePartRendererProps) {
  return part.type === "text" ? <MarkdownRenderer content={part.text} /> : null
}

function ReasoningPartRenderer({ part }: MessagePartRendererProps) {
  const t = useTranslations("agentHistory")
  return part.type === "reasoning_summary" ? (
    <AgentThinking label={t("reasoning.title")} part={part} />
  ) : null
}

function ArtifactPartRenderer({ part }: MessagePartRendererProps) {
  return part.type === "artifact_ref" ? (
    <AgentArtifactReference part={part} />
  ) : null
}

function ToolResultRenderer({ part, nestedContent }: MessagePartRendererProps) {
  const t = useTranslations("agentActivity")
  if (part.type !== "tool_result") return null
  const publicContent = part.summary ?? part.error

  return (
    <div className="grid min-w-0 gap-2">
      <div className="flex min-w-0 items-start gap-2 rounded-[8px] border border-border/60 bg-muted/20 px-3 py-2 text-xs">
        <Badge variant="outline">{t(`status.${part.status}`)}</Badge>
        {publicContent ? (
          <p className="min-w-0 flex-1 whitespace-pre-wrap break-words leading-5 text-foreground/75">
            {publicContent}
          </p>
        ) : null}
      </div>
      {nestedContent}
    </div>
  )
}

function ReferencePartRenderer({ part, onOpenRun }: MessagePartRendererProps) {
  if (!isReferencePart(part)) return null
  return <ReferenceRow part={part} onOpenRun={onOpenRun} />
}

function UnknownPartRenderer({ part }: MessagePartRendererProps) {
  const t = useTranslations("agentHistory")
  if (part.type !== "unknown") return null
  return (
    <div className="grid gap-1 rounded-[10px] border border-border/60 bg-muted/25 px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-foreground/80">
          {t("unknown.title")}
        </span>
        <Badge variant="outline" className="font-mono text-[10px]" translate="no">
          {part.original_type}
        </Badge>
      </div>
      <p className="text-xs leading-5 text-muted-foreground">
        {part.display_text}
      </p>
    </div>
  )
}

function ReferenceRow({
  part,
  onOpenRun,
}: {
  part: ReferencePart
  onOpenRun?: (runId: string) => void
}) {
  const t = useTranslations("agentHistory")
  const reference = referenceView(part)
  const className =
    "flex min-h-11 w-full min-w-0 items-center gap-2 rounded-[8px] px-2.5 py-2 text-left text-xs"
  const content = (
    <>
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
      {part.type === "run_ref" && onOpenRun ? (
        <ChevronRight aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
      ) : null}
    </>
  )

  if (part.type === "run_ref" && onOpenRun) {
    return (
      <button
        type="button"
        className={`${className} transition-colors hover:bg-agent-activity-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40 motion-reduce:transition-none`}
        aria-label={t("reference.openRun", { name: reference.label })}
        onClick={() => onOpenRun(part.run_id)}
      >
        {content}
      </button>
    )
  }

  return <div className={className}>{content}</div>
}

function isReferencePart(part: RenderablePart): part is ReferencePart {
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
    return { kind: "attachment" as const, label: part.filename, detail: part.mime_type }
  }
  if (part.type === "file_ref") {
    return { kind: "file" as const, label: part.label, detail: part.path }
  }
  if (part.type === "directory_ref") {
    return { kind: "directory" as const, label: part.label, detail: part.path }
  }
  if (part.type === "workflow_ref") {
    return { kind: "workflow" as const, label: part.label, detail: part.workflow_id }
  }
  return { kind: "run" as const, label: part.label, detail: part.run_id }
}
