"use client"

import {
  Activity,
  File,
  Folder,
  Paperclip,
  Workflow,
  X,
} from "@/lib/icons"
import { useTranslations } from "next-intl"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  agentAttachmentPreviewUrl,
  type AgentContextInput,
  type AgentContextKind,
} from "@/lib/agent/context"
import type { AppIcon } from "@/lib/icons"

const iconByKind: Record<AgentContextKind, AppIcon> = {
  attachment: Paperclip,
  file: File,
  directory: Folder,
  workflow: Workflow,
  run: Activity,
}

export function AgentContextInputs({
  inputs,
  onRemove,
  disabled = false,
}: {
  inputs: AgentContextInput[]
  onRemove: (inputId: string) => void
  disabled?: boolean
}) {
  const t = useTranslations("agentContext")
  if (inputs.length === 0) return null

  return (
    <ul
      className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1.5"
      aria-label={t("label")}
    >
      {inputs.map((input) => {
        const Icon = iconByKind[input.kind]
        return (
          <li key={input.id} className="min-w-0 max-w-full">
            <Badge
              variant="outline"
              className="max-w-full justify-start gap-1.5 overflow-visible bg-muted/35 pr-0.5"
              title={input.detail ?? undefined}
            >
              <Icon aria-hidden="true" />
              {input.input_part.type === "attachment_ref" ? (
                <a
                  href={agentAttachmentPreviewUrl(
                    input.input_part.attachment_id,
                  )}
                  target="_blank"
                  rel="noreferrer"
                  className="min-w-0 truncate underline-offset-2 hover:underline"
                  translate="no"
                >
                  {input.label}
                </a>
              ) : (
                <span className="min-w-0 truncate" translate="no">
                  {input.label}
                </span>
              )}
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="relative before:absolute before:-inset-1.5"
                disabled={disabled}
                onClick={() => onRemove(input.id)}
                aria-label={t("remove", { label: input.label })}
              >
                <X data-icon="inline-start" aria-hidden="true" />
              </Button>
            </Badge>
          </li>
        )
      })}
    </ul>
  )
}
