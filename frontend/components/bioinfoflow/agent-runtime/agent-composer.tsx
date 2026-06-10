"use client"

import { forwardRef, useEffect, useImperativeHandle, useRef } from "react"
import {
  ClipboardCheck,
  FolderOpen,
  ListTree,
  Paperclip,
  Plus,
  Send,
  Square,
  Stethoscope,
} from "lucide-react"
import { useTranslations } from "next-intl"
import { toast } from "sonner"

import { ModelSelector } from "@/components/bioinfoflow/chat/model-selector"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import type { ModelSelection, ProviderModels } from "@/hooks/use-llm-settings"
import { cn } from "@/lib/utils"

type AgentComposerProps = {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  onStop: () => void
  isRunning: boolean
  disabled?: boolean
  models: ProviderModels[]
  selectedModel: ModelSelection | null
  modelsLoading?: boolean
  onSelectModel: (selection: ModelSelection | null) => void
  className?: string
}

const attachMenuItems = [
  { key: "attachFiles", Icon: Paperclip },
  { key: "browseProjectFiles", Icon: FolderOpen },
  { key: "referenceRun", Icon: ListTree },
  { key: "runPreflight", Icon: ClipboardCheck },
  { key: "diagnoseRun", Icon: Stethoscope },
] as const

export const AgentComposer = forwardRef<HTMLTextAreaElement, AgentComposerProps>(
  function AgentComposer(
    {
      value,
      onChange,
      onSubmit,
      onStop,
      isRunning,
      disabled = false,
      models,
      selectedModel,
      modelsLoading = false,
      onSelectModel,
      className,
    },
    ref,
  ) {
    const t = useTranslations("agentRuntime")
    const canSubmit = !disabled && value.trim().length > 0
    const textareaRef = useRef<HTMLTextAreaElement | null>(null)

    useImperativeHandle(ref, () => textareaRef.current as HTMLTextAreaElement, [])

    const resizeTextarea = (textarea: HTMLTextAreaElement) => {
      const maxHeight = 160
      textarea.style.height = "0px"
      const nextHeight = Math.min(textarea.scrollHeight, maxHeight)
      textarea.style.height = `${nextHeight}px`
      textarea.style.overflowY = textarea.scrollHeight > maxHeight ? "auto" : "hidden"
    }

    useEffect(() => {
      const textarea = textareaRef.current
      if (!textarea) return
      resizeTextarea(textarea)
    }, [value])

    return (
      <div
        className={cn(
          "mx-auto flex w-full max-w-3xl items-end gap-1 rounded-[30px] border border-border/70 bg-card p-2 shadow-xl shadow-foreground/5",
          "focus-within:border-border focus-within:shadow-2xl focus-within:shadow-foreground/10",
          className,
        )}
        data-testid="agent-composer"
      >
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-10 w-10 shrink-0 rounded-full text-muted-foreground hover:bg-muted/70 hover:text-foreground"
              disabled={disabled}
              aria-label={t("attach")}
            >
              <Plus className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="start"
            side="top"
            sideOffset={10}
            className="w-56 rounded-2xl border-border/70 bg-popover p-1.5 shadow-2xl shadow-foreground/10"
          >
            {attachMenuItems.map(({ key, Icon }) => (
              <DropdownMenuItem
                key={key}
                className="rounded-xl px-2.5 py-2 text-sm"
                onSelect={() => toast.info(t("attachMenu.comingSoon"))}
              >
                <Icon className="h-4 w-4" />
                <span>{t(`attachMenu.${key}`)}</span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => {
            resizeTextarea(event.currentTarget)
            onChange(event.target.value)
          }}
          onKeyDown={(event) => {
            if (event.nativeEvent.isComposing) return
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault()
              onSubmit()
            }
          }}
          placeholder={t("composerPlaceholder")}
          className="min-h-11 flex-1 resize-none bg-transparent px-1 py-2.5 text-[15px] leading-6 text-foreground outline-none placeholder:text-muted-foreground"
          rows={1}
          disabled={disabled}
          style={{ overflowY: "hidden" }}
        />
        <div className="hidden shrink-0 sm:block">
          <ModelSelector
            models={models}
            selectedModel={selectedModel}
            onSelectModel={onSelectModel}
            disabled={modelsLoading || disabled}
            allowAuto
            variant="composer"
          />
        </div>
        {isRunning ? (
          <Button
            type="button"
            variant="outline"
            size="icon"
            className="h-10 w-10 shrink-0 rounded-full border-border/70 bg-card"
            onClick={onStop}
            aria-label={t("stop")}
          >
            <Square className="h-4 w-4" />
          </Button>
        ) : (
          <Button
            type="button"
            size="icon"
            className="h-10 w-10 shrink-0 rounded-full"
            onClick={onSubmit}
            disabled={!canSubmit}
            aria-label={t("send")}
          >
            <Send className="h-4 w-4" />
          </Button>
        )}
      </div>
    )
  },
)
