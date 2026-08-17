"use client"

import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import type { ArtifactTranscriptBlock } from "@/lib/agent/conversation-model/types"
import {
  FileCode,
  FileJson,
  FileSpreadsheet,
  FileText,
} from "@/lib/icons"

export function AgentArtifactReference({
  artifact,
  onOpen,
}: {
  artifact: ArtifactTranscriptBlock
  onOpen?: (artifactId: string) => void
}) {
  const t = useTranslations("agentHistory")
  const label = artifact.title ?? artifact.artifactId
  const titleId = `transcript-artifact-${artifact.id}`

  if (!artifact.artifactId) return null

  return (
    <article
      aria-labelledby={titleId}
      className="group flex min-h-[104px] w-full min-w-0 items-center gap-4 rounded-[14px] border border-border/70 bg-transparent px-4 py-3.5 shadow-none transition-colors duration-200 hover:border-border dark:border-white/[0.12] dark:hover:border-white/[0.2]"
      data-artifact-id={artifact.artifactId}
      data-testid="agent-artifact-card"
    >
      <span className="flex size-14 shrink-0 items-center justify-center text-muted-foreground/75 transition-colors duration-200 group-hover:text-muted-foreground">
        <ArtifactIcon artifact={artifact} />
      </span>
      <span className="min-w-0 flex-1">
        <span
          id={titleId}
          className="block truncate text-sm font-medium leading-5 tracking-[-0.01em] text-foreground"
          translate="no"
        >
          {label}
        </span>
        <span className="mt-1.5 block truncate text-xs leading-4 text-muted-foreground">
          {t("artifact.preview")}
        </span>
      </span>
      <Button
        type="button"
        variant="secondary"
        size="sm"
        className="h-9 shrink-0 rounded-lg border-0 bg-muted/75 px-4 text-xs shadow-none hover:bg-muted dark:bg-white/[0.06] dark:hover:bg-white/[0.1]"
        onClick={() => onOpen?.(artifact.artifactId)}
        aria-label={t("artifact.open", { name: label })}
      >
        {t("artifact.action")}
      </Button>
    </article>
  )
}

function ArtifactIcon({ artifact }: { artifact: ArtifactTranscriptBlock }) {
  const mediaType = artifact.mediaType ?? ""
  const filename = artifact.title ?? ""
  if (/spreadsheet|excel/u.test(mediaType) || /\.(xlsx|xls|csv|tsv)$/iu.test(filename)) {
    return <FileSpreadsheet aria-hidden="true" className="size-10 stroke-[1.25]" />
  }
  if (mediaType.includes("json") || filename.toLowerCase().endsWith(".json")) {
    return <FileJson aria-hidden="true" className="size-10 stroke-[1.25]" />
  }
  if (/html|javascript/u.test(mediaType) || /\.(html|htm|js|jsx|ts|tsx)$/iu.test(filename)) {
    return <FileCode aria-hidden="true" className="size-10 stroke-[1.25]" />
  }
  return <FileText aria-hidden="true" className="size-10 stroke-[1.25]" />
}
