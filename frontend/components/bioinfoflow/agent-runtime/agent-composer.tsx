"use client"

import { forwardRef, useCallback, useEffect, useId, useImperativeHandle, useMemo, useRef, useState } from "react"
import {
  ChevronDown,
  ClipboardCheck,
  FolderOpen,
  ListTree,
  Loader2,
  Mic,
  Paperclip,
  Plus,
  Send,
  Square,
  Stethoscope,
  X,
} from "@/lib/icons"
import { useLocale, useTranslations } from "next-intl"
import { toast } from "sonner"

import { ModelSelector } from "@/components/bioinfoflow/chat/model-selector"
import {
  composerInlineTokenClassName,
  composerModeMarkerClassName,
  composerModeToneClassName,
  composerSelectorChipClassName,
  composerSelectorMenuClassName,
} from "@/components/bioinfoflow/composer-selector-chip"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import type { ModelSelection, ProviderModels } from "@/hooks/use-llm-settings"
import { useAnimatedPlaceholder } from "@/hooks/use-animated-placeholder"
import { useVoiceDictation } from "@/hooks/use-voice-dictation"
import type { AgentPermissionUpdateState } from "@/hooks/use-agent-runtime"
import type {
  AgentMode,
  AgentPermissionMode,
  AgentRuntimeFileRefPart,
  AgentRuntimeSkill,
  AgentRuntimeWorkflowMention,
  AgentTokenUsageSummary,
} from "@/lib/agent-runtime"
import { tokenUsageViewFromSummary } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"
import { ContextAttachments } from "./context-attachments"
import {
  ConnectedNodeSelector,
  type ExecutionTargetSelection,
} from "./connected-node-selector"
import { PermissionControl } from "./permission-control"

type AgentComposerProps = {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  onStop: () => void
  isRunning: boolean
  disabled?: boolean
  mode?: AgentMode
  onModeChange?: (mode: AgentMode) => void
  permissionMode?: AgentPermissionMode
  onPermissionModeChange?: (mode: AgentPermissionMode) => void
  permissionUpdate?: AgentPermissionUpdateState
  onRetryPermissionModeChange?: () => void
  models: ProviderModels[]
  selectedModel: ModelSelection | null
  modelsLoading?: boolean
  onSelectModel: (selection: ModelSelection | null) => void
  contextAttachments?: AgentRuntimeFileRefPart[]
  onRemoveContextAttachment?: (path: string) => void
  availableSkills?: AgentRuntimeSkill[]
  activeSkillNames?: string[]
  activeComposerTokens?: AgentComposerInlineToken[]
  skillsLoading?: boolean
  skillsError?: string | null
  onAddActiveSkill?: (name: string) => void
  onRemoveActiveSkill?: (name: string) => void
  availableWorkflowMentions?: AgentRuntimeWorkflowMention[]
  activeWorkflowMentions?: AgentRuntimeWorkflowMention[]
  workflowMentionsLoading?: boolean
  workflowMentionsError?: string | null
  onAddWorkflowMention?: (mention: AgentRuntimeWorkflowMention) => void
  onRemoveWorkflowMention?: (workflowId: string) => void
  tokenUsageSummary?: AgentTokenUsageSummary | null
  executionSelection?: ExecutionTargetSelection
  currentExecutionTargetLabel?: string | null
  onExecutionSelectionChange?: (selection: ExecutionTargetSelection) => void
  compactControls?: boolean
  presentation?: "center" | "dock"
  contextTitle?: string | null
  ariaLabel?: string
  placeholderSuggestions?: readonly string[]
  animatePlaceholder?: boolean
  className?: string
}

export type AgentComposerInlineToken =
  | { kind: "skill"; skill: AgentRuntimeSkill }
  | { kind: "workflow"; workflow: AgentRuntimeWorkflowMention }

const attachMenuItems = [
  { key: "attachFiles", Icon: Paperclip },
  { key: "browseProjectFiles", Icon: FolderOpen },
  { key: "referenceRun", Icon: ListTree },
  { key: "runPreflight", Icon: ClipboardCheck },
  { key: "diagnoseRun", Icon: Stethoscope },
] as const

const agentModeOptions: AgentMode[] = ["execution", "plan"]

export const AgentComposer = forwardRef<HTMLTextAreaElement, AgentComposerProps>(
  function AgentComposer(
    {
      value,
      onChange,
      onSubmit,
      onStop,
      isRunning,
      disabled = false,
      mode = "execution",
      onModeChange,
      permissionMode = "guarded_auto",
      onPermissionModeChange,
      permissionUpdate,
      onRetryPermissionModeChange,
      models,
      selectedModel,
      modelsLoading = false,
      onSelectModel,
      contextAttachments = [],
      onRemoveContextAttachment,
      availableSkills = [],
      activeSkillNames = [],
      activeComposerTokens,
      skillsLoading = false,
      skillsError = null,
      onAddActiveSkill,
      onRemoveActiveSkill,
      availableWorkflowMentions = [],
      activeWorkflowMentions = [],
      workflowMentionsLoading = false,
      workflowMentionsError = null,
      onAddWorkflowMention,
      onRemoveWorkflowMention,
      tokenUsageSummary,
      executionSelection,
      currentExecutionTargetLabel,
      onExecutionSelectionChange,
      compactControls = false,
      presentation = "dock",
      contextTitle,
      ariaLabel,
      placeholderSuggestions = [],
      animatePlaceholder = true,
      className,
    },
    ref,
  ) {
    const t = useTranslations("agentRuntime")
    const textareaRef = useRef<HTMLTextAreaElement | null>(null)
    const voiceInsertionRef = useRef<{ start: number; end: number } | null>(null)
    const latestValueRef = useRef(value)
    const latestOnChangeRef = useRef(onChange)
    useEffect(() => {
      latestValueRef.current = value
      latestOnChangeRef.current = onChange
    }, [onChange, value])
    const commandMenuId = useId()
    const [commandMenuOpen, setCommandMenuOpen] = useState(false)
    const [commandToken, setCommandToken] = useState<ComposerCommandToken | null>(null)
    const [highlightedCommandIndex, setHighlightedCommandIndex] = useState(0)
    const [focused, setFocused] = useState(false)
    const insertVoiceTranscript = useCallback(
      (text: string) => {
        const selection = voiceInsertionRef.current
        const latestValue = latestValueRef.current
        const start = selection?.start ?? latestValue.length
        const end = selection?.end ?? start
        const prefix = latestValue.slice(0, start)
        const suffix = latestValue.slice(end)
        const needsLeadingSpace = needsVoiceBoundarySpace(prefix.at(-1), text.at(0))
        const needsTrailingSpace = needsVoiceBoundarySpace(text.at(-1), suffix.at(0))
        const inserted = `${needsLeadingSpace ? " " : ""}${text}${needsTrailingSpace ? " " : ""}`
        const nextValue = `${prefix}${inserted}${suffix}`
        const caret = prefix.length + inserted.length
        latestOnChangeRef.current(nextValue)
        window.requestAnimationFrame(() => {
          textareaRef.current?.focus()
          textareaRef.current?.setSelectionRange(caret, caret)
        })
      },
      [],
    )
    const voice = useVoiceDictation({
      onTranscript: insertVoiceTranscript,
      onError: () => toast.error(t("voice.failed")),
    })
    const { cancel: cancelVoice, state: voiceState } = voice
    const voiceBusy = voiceState === "recording" || voiceState === "transcribing"
    const canSubmit = !disabled && !voiceBusy && value.trim().length > 0
    useEffect(() => {
      if (voiceState !== "recording") return
      const cancelOnEscape = (event: KeyboardEvent) => {
        if (event.key !== "Escape") return
        event.preventDefault()
        cancelVoice()
        toast.info(t("voice.cancelled"))
      }
      window.addEventListener("keydown", cancelOnEscape)
      return () => window.removeEventListener("keydown", cancelOnEscape)
    }, [cancelVoice, t, voiceState])
    const isCenterPresentation = presentation === "center"
    const animatedPlaceholder = useAnimatedPlaceholder({
      enabled:
        animatePlaceholder && !disabled && placeholderSuggestions.length > 0,
      focused,
      value,
      strings: placeholderSuggestions,
    })
    const visualPlaceholder = placeholderSuggestions.length
      ? animatedPlaceholder
      : t("composerPlaceholder")
    const stableAriaLabel = ariaLabel ?? t("composerPlaceholder")

    useImperativeHandle(ref, () => textareaRef.current as HTMLTextAreaElement, [])

    const resizeTextarea = (textarea: HTMLTextAreaElement) => {
      const maxHeight = 160
      textarea.style.height = "0px"
      const nextHeight = Math.min(textarea.scrollHeight, maxHeight)
      textarea.style.height = `${nextHeight}px`
      textarea.style.overflowY = textarea.scrollHeight > maxHeight ? "auto" : "hidden"
    }

    const activeSkillSet = useMemo(() => new Set(activeSkillNames), [activeSkillNames])
    const activeSkills = useMemo(
      () =>
        activeSkillNames.map((name) =>
          availableSkills.find((skill) => skill.name === name) ?? fallbackSkill(name),
        ),
      [activeSkillNames, availableSkills],
    )
    const visibleComposerTokens = useMemo<AgentComposerInlineToken[]>(
      () =>
        activeComposerTokens ??
        [
          ...activeWorkflowMentions.map((workflow) => ({
            kind: "workflow" as const,
            workflow,
          })),
          ...activeSkills.map((skill) => ({ kind: "skill" as const, skill })),
        ],
      [activeComposerTokens, activeSkills, activeWorkflowMentions],
    )
    const skillOptions = useMemo(
      () =>
        availableSkills
          .filter((skill) => !activeSkillSet.has(skill.name))
          .filter((skill) =>
            commandToken?.kind === "skill"
              ? skillMatchesQuery(skill, commandToken.query)
              : false,
          )
          .slice(0, 8),
      [activeSkillSet, availableSkills, commandToken],
    )
    const activeWorkflowMentionSet = useMemo(
      () => new Set(activeWorkflowMentions.map((workflow) => workflow.id)),
      [activeWorkflowMentions],
    )
    const workflowMentionOptions = useMemo(
      () =>
        availableWorkflowMentions
          .filter((workflow) => !activeWorkflowMentionSet.has(workflow.id))
          .filter((workflow) =>
            commandToken?.kind === "workflow"
              ? workflowMentionMatchesQuery(workflow, commandToken.query)
              : false,
          )
          .slice(0, 8),
      [activeWorkflowMentionSet, availableWorkflowMentions, commandToken],
    )
    const commandOptions: ComposerCommandOption[] = useMemo(
      () =>
        commandToken?.kind === "workflow"
          ? workflowMentionOptions.map((workflow) => ({ kind: "workflow", workflow }))
          : skillOptions.map((skill) => ({ kind: "skill", skill })),
      [commandToken?.kind, skillOptions, workflowMentionOptions],
    )
    const visibleHighlightedCommandIndex = commandOptions.length
      ? Math.min(highlightedCommandIndex, commandOptions.length - 1)
      : 0
    const activeCommandOptionId =
      commandMenuOpen && commandOptions.length
        ? commandOptionId(commandMenuId, visibleHighlightedCommandIndex)
        : undefined
    const commandTextareaPopupProps = {
      "aria-haspopup": "listbox" as const,
      "aria-expanded": commandMenuOpen,
      "aria-controls": commandMenuOpen ? commandMenuId : undefined,
      "aria-activedescendant": activeCommandOptionId,
    }

    const closeCommandMenu = useCallback(() => {
      setCommandMenuOpen(false)
      setCommandToken(null)
      setHighlightedCommandIndex(0)
    }, [])

    const updateCommandMenu = useCallback(
      (textarea: HTMLTextAreaElement) => {
        const token = composerCommandTokenAt(textarea.value, textarea.selectionStart ?? textarea.value.length)
        const canHandleToken =
          token?.kind === "skill"
            ? Boolean(onAddActiveSkill)
            : token?.kind === "workflow"
              ? Boolean(onAddWorkflowMention)
              : false
        if (!token || disabled || !canHandleToken) {
          closeCommandMenu()
          return
        }
        setCommandToken(token)
        setHighlightedCommandIndex(0)
        setCommandMenuOpen(true)
      },
      [closeCommandMenu, disabled, onAddActiveSkill, onAddWorkflowMention],
    )

    const selectSkill = useCallback(
      (skill: AgentRuntimeSkill) => {
        const textarea = textareaRef.current
        const token = commandToken?.kind === "skill"
          ? commandToken
          : textarea
            ? composerCommandTokenAt(value, textarea.selectionStart ?? value.length)
            : null
        if (!token) return
        const nextValue = `${value.slice(0, token.start)}${value.slice(token.end)}`
        onChange(nextValue)
        onAddActiveSkill?.(skill.name)
        closeCommandMenu()
        window.requestAnimationFrame(() => {
          textarea?.focus()
          textarea?.setSelectionRange(token.start, token.start)
        })
      },
      [closeCommandMenu, commandToken, onAddActiveSkill, onChange, value],
    )

    const selectWorkflowMention = useCallback(
      (workflow: AgentRuntimeWorkflowMention) => {
        const textarea = textareaRef.current
        const token = commandToken?.kind === "workflow"
          ? commandToken
          : textarea
            ? composerCommandTokenAt(value, textarea.selectionStart ?? value.length)
            : null
        if (!token) return
        const nextValue = `${value.slice(0, token.start)}${value.slice(token.end)}`
        onChange(nextValue)
        onAddWorkflowMention?.(workflow)
        closeCommandMenu()
        window.requestAnimationFrame(() => {
          textarea?.focus()
          textarea?.setSelectionRange(token.start, token.start)
        })
      },
      [closeCommandMenu, commandToken, onAddWorkflowMention, onChange, value],
    )

    const selectCommandOption = useCallback(
      (option: ComposerCommandOption) => {
        if (option.kind === "skill") {
          selectSkill(option.skill)
          return
        }
        selectWorkflowMention(option.workflow)
      },
      [selectSkill, selectWorkflowMention],
    )

    const removePreviousInlineToken = useCallback(() => {
      const lastToken = visibleComposerTokens.at(-1)
      if (!lastToken) return false
      if (lastToken.kind === "skill") {
        onRemoveActiveSkill?.(lastToken.skill.name)
        return true
      }
      onRemoveWorkflowMention?.(lastToken.workflow.id)
      return true
    }, [
      onRemoveActiveSkill,
      onRemoveWorkflowMention,
      visibleComposerTokens,
    ])

    useEffect(() => {
      const textarea = textareaRef.current
      if (!textarea) return
      resizeTextarea(textarea)
    }, [value])

    return (
      <div
        className={cn(
          "mx-auto flex w-full max-w-[42rem] flex-col gap-1.5 rounded-[24px] border border-border bg-card p-1.5 shadow-[0_1px_2px_rgba(15,15,15,0.035)] transition-[border-color,box-shadow] duration-200",
          "focus-within:border-foreground/24 hover:border-foreground/14",
          isCenterPresentation && "p-2",
          className,
        )}
        data-testid="agent-composer"
        data-presentation={presentation}
        data-compact-controls={compactControls ? "true" : "false"}
      >
        {contextTitle ? (
          <div className="flex min-h-7 min-w-0 items-center gap-2 px-3 pt-1.5 text-xs font-medium text-muted-foreground">
            <span className="min-w-0 truncate text-foreground/70">{contextTitle}</span>
          </div>
        ) : null}
        <ContextAttachments
          attachments={contextAttachments}
          onRemove={onRemoveContextAttachment ?? (() => {})}
        />
        <div className="relative">
          <div
            className={cn(
              "flex w-full min-w-0 flex-wrap items-start gap-x-1.5 gap-y-1.5 px-3 py-2",
              isCenterPresentation ? "min-h-[80px]" : "min-h-12",
            )}
            data-testid="agent-inline-token-flow"
          >
            <ComposerInlineTokens
              tokens={visibleComposerTokens}
              disabled={disabled}
              onRemoveActiveSkill={onRemoveActiveSkill}
              onRemoveWorkflowMention={onRemoveWorkflowMention}
            />
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(event) => {
              resizeTextarea(event.currentTarget)
              onChange(event.target.value)
              updateCommandMenu(event.currentTarget)
            }}
            onKeyDown={(event) => {
              if (event.nativeEvent.isComposing) return
              if (
                event.key === "Backspace" &&
                event.currentTarget.selectionStart === 0 &&
                event.currentTarget.selectionEnd === 0 &&
                removePreviousInlineToken()
              ) {
                event.preventDefault()
                return
              }
              if (commandMenuOpen) {
                if (event.key === "ArrowDown") {
                  event.preventDefault()
                  setHighlightedCommandIndex((current) =>
                    commandOptions.length ? (current + 1) % commandOptions.length : 0,
                  )
                  return
                }
                if (event.key === "ArrowUp") {
                  event.preventDefault()
                  setHighlightedCommandIndex((current) =>
                    commandOptions.length
                      ? (current - 1 + commandOptions.length) % commandOptions.length
                      : 0,
                  )
                  return
                }
                if (event.key === "Escape") {
                  event.preventDefault()
                  closeCommandMenu()
                  return
                }
                if ((event.key === "Enter" || event.key === "Tab") && commandOptions[visibleHighlightedCommandIndex]) {
                  event.preventDefault()
                  selectCommandOption(commandOptions[visibleHighlightedCommandIndex])
                  return
                }
              }
              if (event.key === "Tab" && event.shiftKey && onModeChange) {
                event.preventDefault()
                onModeChange(mode === "plan" ? "execution" : "plan")
                return
              }
              if (event.key === "Enter" && !event.shiftKey && !voiceBusy) {
                event.preventDefault()
                onSubmit()
              }
            }}
            onClick={(event) => updateCommandMenu(event.currentTarget)}
            onFocus={() => setFocused(true)}
            onBlur={() => {
              setFocused(false)
              window.setTimeout(closeCommandMenu, 120)
            }}
            placeholder={visualPlaceholder}
            aria-label={stableAriaLabel}
            {...commandTextareaPopupProps}
            className={cn(
              "min-w-[12rem] flex-1 resize-none bg-transparent px-0 py-0.5 text-[14px] leading-5 text-foreground outline-none placeholder:text-muted-foreground/64",
              isCenterPresentation ? "min-h-[64px]" : "min-h-6",
            )}
            rows={1}
            disabled={disabled}
            style={{ overflowY: "hidden" }}
          />
          </div>
          {commandMenuOpen && commandToken ? (
            <ComposerCommandMenu
              id={commandMenuId}
              token={commandToken}
              options={commandOptions}
              loading={commandToken.kind === "workflow" ? workflowMentionsLoading : skillsLoading}
              error={commandToken.kind === "workflow" ? workflowMentionsError : skillsError}
              highlightedIndex={visibleHighlightedCommandIndex}
              onHover={setHighlightedCommandIndex}
              onSelect={selectCommandOption}
            />
          ) : null}
        </div>
        <div className="flex min-h-8 flex-wrap items-center gap-1 px-0.5">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-8 w-8 shrink-0 rounded-full border-0 bg-muted p-0 text-foreground/68 shadow-none hover:bg-accent hover:text-foreground"
                disabled={disabled}
                aria-label={t("attach")}
                data-composer-chip="true"
              >
                <Plus className="h-3.5 w-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              align="start"
              side="top"
              sideOffset={10}
              className={cn("w-52", composerSelectorMenuClassName)}
            >
              {attachMenuItems.map(({ key, Icon }) => (
                <DropdownMenuItem
                  key={key}
                  className="rounded-[7px] px-2 py-1.5 text-xs"
                  onSelect={() => toast.info(t("attachMenu.comingSoon"))}
                >
                  <Icon className="h-3.5 w-3.5" />
                  <span>{t(`attachMenu.${key}`)}</span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>

          <div
            className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5"
            data-testid="agent-composer-controls"
          >
            {onModeChange ? (
              <span
                className={cn(
                  "hidden shrink-0 sm:inline-flex",
                )}
                data-testid="agent-mode-chip-shell"
              >
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className={cn(
                        composerSelectorChipClassName,
                        composerModeToneClassName[mode],
                        "shrink-0",
                        compactControls ? "max-w-9 px-2" : "max-w-[7rem] px-2",
                      )}
                      data-composer-chip="true"
                      data-mode={mode}
                      data-testid="agent-mode-chip"
                      disabled={disabled}
                      aria-label={t("mode.label")}
                    >
                      <span
                        aria-hidden="true"
                        className={cn(
                          "h-1.5 w-1.5 shrink-0 rounded-full",
                          composerModeMarkerClassName[mode],
                        )}
                        data-testid="agent-mode-chip-marker"
                      />
                      <span className={cn(compactControls && "sr-only")}>
                        {t(mode === "plan" ? "mode.plan" : "mode.act")}
                      </span>
                      <ChevronDown className={cn("h-2.5 w-2.5 shrink-0 opacity-60", compactControls && "hidden")} />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent
                    align="end"
                    side="top"
                    sideOffset={10}
                    className={cn("w-36", composerSelectorMenuClassName)}
                  >
                    {agentModeOptions.map((optionMode) => (
                      <DropdownMenuItem
                        key={optionMode}
                        className="items-center gap-1.5 rounded-[7px] px-2 py-1.5 text-xs"
                        onSelect={() => onModeChange(optionMode)}
                      >
                        <span
                          className={cn(
                            "h-1.5 w-1.5 shrink-0 rounded-full",
                            composerModeMarkerClassName[optionMode],
                          )}
                        />
                        <span className="flex-1">
                          {t(optionMode === "plan" ? "mode.plan" : "mode.act")}
                        </span>
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
              </span>
            ) : null}
            <div
              className={cn(
                "hidden min-w-0 shrink sm:flex sm:items-center",
                compactControls ? "max-w-9" : "max-w-[11rem]",
              )}
            >
              <ModelSelector
                models={models}
                selectedModel={selectedModel}
                onSelectModel={onSelectModel}
                disabled={modelsLoading || disabled}
                allowAuto
                variant="composer"
                compact={compactControls}
              />
            </div>
            <ConnectedNodeSelector
              disabled={disabled}
              compact={compactControls}
              value={executionSelection}
              currentTargetLabel={currentExecutionTargetLabel}
              onChange={onExecutionSelectionChange}
            />
            {onPermissionModeChange ? (
              <PermissionControl
                mode={permissionMode}
                onModeChange={onPermissionModeChange}
                update={permissionUpdate}
                onRetry={onRetryPermissionModeChange}
                remote={selectionIncludesRemote(executionSelection)}
                disabled={disabled}
                compact={compactControls}
              />
            ) : null}
            <AgentTokenUsageBadge
              summary={tokenUsageSummary}
              compact={compactControls}
            />
            <div className="ml-auto flex min-w-0 items-center gap-1.5">
              {voice.state === "recording" ? (
                <div
                  className="hidden items-center gap-1.5 text-[11px] tabular-nums text-destructive/80 sm:flex"
                  role="status"
                >
                  <span>{t("voice.recording", { time: formatVoiceTime(voice.elapsedSeconds) })}</span>
                  <span className="flex h-3 items-end gap-0.5" aria-hidden="true">
                    {[0.12, 0.28, 0.44, 0.6, 0.76].map((threshold, index) => (
                      <span
                        key={threshold}
                        className={cn(
                          "w-0.5 rounded-full bg-destructive/25 transition-[height,background-color] duration-100 motion-reduce:transition-none",
                          voice.level >= threshold && "bg-destructive/75",
                        )}
                        style={{ height: `${4 + index * 1.5}px` }}
                      />
                    ))}
                  </span>
                </div>
              ) : voice.state === "transcribing" ? (
                <span className="hidden items-center gap-1 text-[11px] text-muted-foreground sm:flex" role="status">
                  <Loader2 className="h-3 w-3 animate-spin motion-reduce:animate-none" />
                  {t("voice.transcribing")}
                </span>
              ) : voice.state === "error" ? (
                <button
                  type="button"
                  className="hidden text-[11px] text-destructive/80 hover:text-destructive sm:inline"
                  onClick={voice.resetError}
                >
                  {t("voice.failed")}
                </button>
              ) : null}
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className={cn(
                  "h-8 w-8 shrink-0 rounded-[10px] text-foreground/58 hover:bg-muted hover:text-foreground",
                  voice.state === "recording" && "bg-destructive/10 text-destructive hover:bg-destructive/15 hover:text-destructive",
                )}
                onClick={() => {
                  if (voice.state === "recording") {
                    voice.stop()
                    return
                  }
                  const textarea = textareaRef.current
                  voiceInsertionRef.current = textarea
                    ? { start: textarea.selectionStart, end: textarea.selectionEnd }
                    : { start: value.length, end: value.length }
                  void voice.start()
                }}
                disabled={disabled || !voice.available || voice.state === "transcribing"}
                aria-label={t(voice.state === "recording" ? "voice.stop" : "voice.start")}
                title={!voice.available ? t("voice.unavailable") : undefined}
              >
                {voice.state === "recording" ? (
                  <Square className="h-3.5 w-3.5 fill-current" />
                ) : voice.state === "transcribing" ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />
                ) : (
                  <Mic className="h-3.5 w-3.5" />
                )}
              </Button>
              {isRunning ? (
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  className="h-8 w-8 shrink-0 rounded-[10px] border-border/70 bg-card"
                  onClick={onStop}
                  aria-label={t("stop")}
                >
                  <Square className="h-3.5 w-3.5" />
                </Button>
              ) : null}
              <Button
                type="button"
                size="icon"
                className="h-8 w-8 shrink-0 rounded-[10px] bg-primary text-primary-foreground shadow-none hover:bg-primary/88 focus-visible:ring-primary/25"
                onClick={onSubmit}
                disabled={!canSubmit}
                aria-label={t("send")}
              >
                <Send className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </div>
      </div>
    )
  },
)

function formatVoiceTime(seconds: number) {
  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  return `${minutes}:${remainder.toString().padStart(2, "0")}`
}

function needsVoiceBoundarySpace(left?: string, right?: string) {
  if (!left || !right || /\s/u.test(left) || /\s/u.test(right)) return false
  const latinOrNumber = /[\p{Script=Latin}\p{N}]/u
  const wordCharacter = /[\p{L}\p{N}]/u
  return (
    wordCharacter.test(left) &&
    wordCharacter.test(right) &&
    (latinOrNumber.test(left) || latinOrNumber.test(right))
  )
}

type ComposerCommandToken = {
  kind: "skill" | "workflow"
  start: number
  end: number
  query: string
}

type ComposerCommandOption =
  | { kind: "skill"; skill: AgentRuntimeSkill }
  | { kind: "workflow"; workflow: AgentRuntimeWorkflowMention }

function ComposerCommandMenu({
  id,
  token,
  options,
  loading,
  error,
  highlightedIndex,
  onHover,
  onSelect,
}: {
  id: string
  token: ComposerCommandToken
  options: ComposerCommandOption[]
  loading: boolean
  error?: string | null
  highlightedIndex: number
  onHover: (index: number) => void
  onSelect: (option: ComposerCommandOption) => void
}) {
  const t = useTranslations("agentRuntime")
  const isWorkflow = token.kind === "workflow"
  const statusText = error
    ? t(isWorkflow ? "workflows.loadFailed" : "skills.loadFailed")
    : loading
      ? t(isWorkflow ? "workflows.loading" : "skills.loading")
      : token.query
        ? t(isWorkflow ? "workflows.noMatches" : "skills.noMatches")
        : t(isWorkflow ? "workflows.empty" : "skills.empty")

  return (
    <div
      id={id}
      className={cn(
        "absolute bottom-[calc(100%+0.5rem)] left-3 z-50 w-[min(28rem,calc(100vw-2rem))] overflow-hidden rounded-[10px] border border-border bg-popover p-1 shadow-[0_8px_24px_rgba(15,15,15,0.06)]",
        composerSelectorMenuClassName,
      )}
      data-testid="agent-command-menu"
      role="listbox"
      aria-label={t(isWorkflow ? "workflows.menuTitle" : "skills.menuTitle")}
    >
      <div
        className="px-2.5 py-1.5 text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground/70"
        data-testid={isWorkflow ? "agent-workflow-menu" : "agent-skill-menu"}
      >
        {t(isWorkflow ? "workflows.menuTitle" : "skills.menuTitle")}
      </div>
      {options.length ? (
        <div className="grid gap-1">
          {options.map((option, index) => (
            <button
              id={commandOptionId(id, index)}
              key={commandOptionKey(option)}
              type="button"
              className={cn(
                "grid w-full gap-0.5 rounded-[7px] px-2.5 py-2 text-left transition-colors",
                index === highlightedIndex ? "bg-accent text-accent-foreground" : "hover:bg-accent/65",
              )}
              role="option"
              aria-selected={index === highlightedIndex}
              onMouseEnter={() => onHover(index)}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => onSelect(option)}
              data-testid="agent-command-option"
            >
              {option.kind === "skill" ? (
                <SkillCommandOptionContent skill={option.skill} />
              ) : (
                <WorkflowCommandOptionContent workflow={option.workflow} />
              )}
            </button>
          ))}
        </div>
      ) : (
        <div
          className="px-2.5 py-3 text-sm text-muted-foreground"
          data-testid={isWorkflow ? "agent-workflow-menu-empty" : "agent-skill-menu-empty"}
        >
          {statusText}
        </div>
      )}
    </div>
  )
}

function SkillCommandOptionContent({ skill }: { skill: AgentRuntimeSkill }) {
  return (
    <span data-testid="agent-skill-option">
      <span className="flex min-w-0 items-center gap-2 text-sm font-medium">
        <span className="min-w-0 truncate">/{skill.name}</span>
        <span className="shrink-0 text-[11px] text-muted-foreground">{skill.version}</span>
      </span>
      <span className="line-clamp-2 text-xs leading-5 text-muted-foreground">
        {skill.description}
      </span>
    </span>
  )
}

function WorkflowCommandOptionContent({
  workflow,
}: {
  workflow: AgentRuntimeWorkflowMention
}) {
  const t = useTranslations("agentRuntime")
  return (
    <span className="grid gap-0.5">
      <span className="flex min-w-0 items-center gap-2 text-sm font-medium">
        <span className="min-w-0 truncate">@{workflow.name}</span>
        <span className="shrink-0 text-[11px] text-muted-foreground">
          {workflow.version}
        </span>
      </span>
      <span className="line-clamp-1 text-xs leading-5 text-muted-foreground">
        {workflow.engine} · {workflow.source}
        {workflow.pinned ? ` · ${t("workflows.pinned")}` : ""}
        {workflow.description ? ` · ${workflow.description}` : ""}
      </span>
    </span>
  )
}

function commandOptionKey(option: ComposerCommandOption) {
  return option.kind === "skill" ? `skill:${option.skill.name}` : `workflow:${option.workflow.id}`
}

function commandOptionId(menuId: string, index: number) {
  return `${menuId}-option-${index}`
}

function composerCommandTokenAt(value: string, cursor: number): ComposerCommandToken | null {
  let start = cursor
  while (start > 0 && !/\s/.test(value[start - 1])) start -= 1
  const token = value.slice(start, cursor)
  const marker = token[0]
  if (marker !== "/" && marker !== "@") return null
  const query = token.slice(1)
  if (!/^[A-Za-z0-9._-]*$/.test(query)) return null
  return { kind: marker === "/" ? "skill" : "workflow", start, end: cursor, query }
}

function skillMatchesQuery(skill: AgentRuntimeSkill, query: string) {
  const normalized = query.trim().toLowerCase()
  if (!normalized) return true
  return [skill.name, skill.description, skill.category, ...skill.tags]
    .filter(Boolean)
    .some((value) => String(value).toLowerCase().includes(normalized))
}

function workflowMentionMatchesQuery(
  workflow: AgentRuntimeWorkflowMention,
  query: string,
) {
  const normalized = query.trim().toLowerCase()
  if (!normalized) return true
  return [
    workflow.name,
    workflow.version,
    workflow.description,
    workflow.engine,
    workflow.source,
  ]
    .filter(Boolean)
    .some((value) => String(value).toLowerCase().includes(normalized))
}

function fallbackSkill(name: string): AgentRuntimeSkill {
  return {
    name,
    version: "",
    description: name,
    tags: [],
  }
}

function ComposerInlineTokens({
  tokens,
  disabled,
  onRemoveActiveSkill,
  onRemoveWorkflowMention,
}: {
  tokens: AgentComposerInlineToken[]
  disabled: boolean
  onRemoveActiveSkill?: (name: string) => void
  onRemoveWorkflowMention?: (workflowId: string) => void
}) {
  const t = useTranslations("agentRuntime")
  if (!tokens.length) return null

  return (
    <>
      {tokens.map((token) => {
        if (token.kind === "skill") {
          return (
            <span
              key={`skill:${token.skill.name}`}
              className={cn(composerInlineTokenClassName, "max-w-[14rem]")}
              data-testid="agent-inline-skill-token"
              role="group"
              aria-label={`/${token.skill.name}`}
            >
              <span className="min-w-0 truncate" translate="no">/{token.skill.name}</span>
              <button
                type="button"
                className="-mr-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-[4px] text-muted-foreground transition-colors hover:bg-background/80 hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring/35"
                onClick={() => onRemoveActiveSkill?.(token.skill.name)}
                disabled={disabled}
                aria-label={t("skills.remove", { name: token.skill.name })}
              >
                <X className="h-3 w-3" />
              </button>
            </span>
          )
        }
        const workflow = token.workflow
        return (
          <span
            key={`workflow:${workflow.id}`}
            className={cn(composerInlineTokenClassName, "max-w-[16rem]")}
            data-testid="agent-inline-workflow-token"
            role="group"
            aria-label={`@${workflowRemoveName(workflow)}`}
          >
            <span className="min-w-0 truncate" translate="no">@{workflow.name}</span>
            <span
              className="shrink-0 text-[10px] font-normal leading-none text-muted-foreground/78"
              title={`${workflow.name} ${workflow.version}`}
              translate="no"
            >
              {workflow.version}
            </span>
            <button
              type="button"
              className="-mr-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-[4px] text-muted-foreground transition-colors hover:bg-background/80 hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring/35"
              onClick={() => onRemoveWorkflowMention?.(workflow.id)}
              disabled={disabled}
              aria-label={t("workflows.remove", { name: workflowRemoveName(workflow) })}
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        )
      })}
    </>
  )
}

function workflowRemoveName(workflow: AgentRuntimeWorkflowMention) {
  const version = workflow.version.trim()
  return version ? `${workflow.name} ${version}` : workflow.name
}

function AgentTokenUsageBadge({
  summary,
  compact,
}: {
  summary?: AgentTokenUsageSummary | null
  compact?: boolean
}) {
  const t = useTranslations("agentRuntime")
  const locale = useLocale()
  const view = tokenUsageViewFromSummary(summary, locale)
  if (!view) return null

  const display = compact
    ? t("tokenUsage.compactDisplay", { value: view.totalLabel })
    : t("tokenUsage.display", { value: view.totalLabel })
  const ariaLabel = t("tokenUsage.aria", {
    total: view.totalLabel,
    input: view.inputLabel,
    output: view.outputLabel,
  })
  const toneClass =
    view.status === "critical"
      ? "border-error-border bg-error-muted text-error-foreground"
      : view.status === "warning"
        ? "border-foreground/12 bg-foreground/[0.045] text-foreground/72"
        : ""

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={ariaLabel}
          className={cn(
            composerSelectorChipClassName,
            "hidden shrink-0 items-center tabular-nums focus-visible:outline-none sm:inline-flex",
            compact ? "max-w-[5.75rem]" : "max-w-[8rem]",
            toneClass,
          )}
          data-composer-chip="true"
        >
          <span className="min-w-0 truncate">{display}</span>
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        side="top"
        sideOffset={10}
        className="w-64 rounded-xl border-border bg-popover p-3 shadow-[0_14px_34px_rgba(15,15,15,0.06)]"
      >
        <div className="grid gap-3">
          <div className="flex items-baseline justify-between gap-3">
            <div className="text-xs font-medium text-muted-foreground">
              {t("tokenUsage.title")}
            </div>
            <div className="font-mono text-sm font-semibold tabular-nums text-foreground">
              {view.percentUsed == null ? view.totalLabel : `${view.percentUsed}%`}
            </div>
          </div>
          {view.percentUsed == null ? null : (
            <div className="grid gap-1.5">
              <div className="h-1.5 overflow-hidden rounded-sm bg-muted">
                <div
                  className={cn(
                    "h-full rounded-sm transition-[width] duration-200",
                    view.status === "critical"
                      ? "bg-error"
                      : view.status === "warning"
                        ? "bg-foreground/45"
                        : "bg-foreground/55",
                  )}
                  style={{ width: `${view.percentUsed}%` }}
                />
              </div>
              <div className="flex justify-between text-[11px] text-muted-foreground">
                <span>{t("tokenUsage.used")}</span>
                <span>
                  {view.percentRemaining}% {t("tokenUsage.remaining")}
                </span>
              </div>
            </div>
          )}
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
            <TokenUsageStat label={t("tokenUsage.input")} value={view.inputLabel} />
            <TokenUsageStat label={t("tokenUsage.output")} value={view.outputLabel} />
            {view.contextWindowLabel ? (
              <TokenUsageStat
                label={t("tokenUsage.window")}
                value={view.contextWindowLabel}
              />
            ) : null}
            {view.maxOutputLabel ? (
              <TokenUsageStat
                label={t("tokenUsage.maxOutput")}
                value={view.maxOutputLabel}
              />
            ) : null}
            {view.cachedInputLabel ? (
              <TokenUsageStat
                label={t("tokenUsage.cached")}
                value={view.cachedInputLabel}
              />
            ) : null}
            {view.reasoningLabel ? (
              <TokenUsageStat
                label={t("tokenUsage.reasoning")}
                value={view.reasoningLabel}
              />
            ) : null}
          </dl>
        </div>
      </PopoverContent>
    </Popover>
  )
}

function TokenUsageStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-0.5">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-mono text-sm font-medium tabular-nums text-foreground">
        {value}
      </dd>
    </div>
  )
}

function selectionIncludesRemote(selection?: ExecutionTargetSelection) {
  if (!selection) return false
  if (selection.mode === "auto") return true
  return selection.targetIds.some((targetId) => targetId !== "local")
}
