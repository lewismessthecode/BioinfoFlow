"use client"

import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react"
import {
  ChevronDown,
  ClipboardCheck,
  FolderOpen,
  ListTree,
  Paperclip,
  Plus,
  Send,
  ShieldCheck,
  ShieldQuestion,
  Square,
  Stethoscope,
  Unlock,
  X,
} from "lucide-react"
import { useLocale, useTranslations } from "next-intl"
import { toast } from "sonner"

import { ModelSelector } from "@/components/bioinfoflow/chat/model-selector"
import {
  composerModeMarkerClassName,
  composerModeToneClassName,
  composerSelectorChipClassName,
  composerSelectorIconClassName,
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
import type {
  AgentMode,
  AgentPermissionMode,
  AgentRuntimeFileRefPart,
  AgentRuntimeSkill,
  AgentTokenUsageSummary,
} from "@/lib/agent-runtime"
import { tokenUsageViewFromSummary } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"
import { ContextAttachments } from "./context-attachments"
import { ConnectedNodeSelector } from "./connected-node-selector"

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
  models: ProviderModels[]
  selectedModel: ModelSelection | null
  modelsLoading?: boolean
  onSelectModel: (selection: ModelSelection | null) => void
  contextAttachments?: AgentRuntimeFileRefPart[]
  onRemoveContextAttachment?: (path: string) => void
  availableSkills?: AgentRuntimeSkill[]
  activeSkillNames?: string[]
  skillsLoading?: boolean
  skillsError?: string | null
  onAddActiveSkill?: (name: string) => void
  onRemoveActiveSkill?: (name: string) => void
  tokenUsageSummary?: AgentTokenUsageSummary | null
  selectedRemoteConnectionId?: string
  onRemoteConnectionChange?: (connectionId: string) => void
  compactControls?: boolean
  presentation?: "center" | "dock"
  contextTitle?: string | null
  className?: string
}

const attachMenuItems = [
  { key: "attachFiles", Icon: Paperclip },
  { key: "browseProjectFiles", Icon: FolderOpen },
  { key: "referenceRun", Icon: ListTree },
  { key: "runPreflight", Icon: ClipboardCheck },
  { key: "diagnoseRun", Icon: Stethoscope },
] as const

const permissionOptions: Array<{
  mode: AgentPermissionMode
  Icon: typeof ShieldQuestion
}> = [
  { mode: "ask_each_action", Icon: ShieldQuestion },
  { mode: "guarded_auto", Icon: ShieldCheck },
  { mode: "bypass", Icon: Unlock },
]

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
      models,
      selectedModel,
      modelsLoading = false,
      onSelectModel,
      contextAttachments = [],
      onRemoveContextAttachment,
      availableSkills = [],
      activeSkillNames = [],
      skillsLoading = false,
      skillsError = null,
      onAddActiveSkill,
      onRemoveActiveSkill,
      tokenUsageSummary,
      selectedRemoteConnectionId,
      onRemoteConnectionChange,
      compactControls = false,
      presentation = "dock",
      contextTitle,
      className,
    },
    ref,
  ) {
    const t = useTranslations("agentRuntime")
    const PermissionIcon =
      permissionOptions.find((option) => option.mode === permissionMode)?.Icon ?? ShieldCheck
    const canSubmit = !disabled && value.trim().length > 0
    const textareaRef = useRef<HTMLTextAreaElement | null>(null)
    const [skillMenuOpen, setSkillMenuOpen] = useState(false)
    const [skillQuery, setSkillQuery] = useState("")
    const [skillToken, setSkillToken] = useState<SkillSlashToken | null>(null)
    const [highlightedSkillIndex, setHighlightedSkillIndex] = useState(0)
    const isCenterPresentation = presentation === "center"

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
    const skillOptions = useMemo(
      () =>
        availableSkills
          .filter((skill) => !activeSkillSet.has(skill.name))
          .filter((skill) => skillMatchesQuery(skill, skillQuery))
          .slice(0, 8),
      [activeSkillSet, availableSkills, skillQuery],
    )
    const visibleHighlightedSkillIndex = skillOptions.length
      ? Math.min(highlightedSkillIndex, skillOptions.length - 1)
      : 0

    const closeSkillMenu = useCallback(() => {
      setSkillMenuOpen(false)
      setSkillToken(null)
      setSkillQuery("")
      setHighlightedSkillIndex(0)
    }, [])

    const updateSkillMenu = useCallback(
      (textarea: HTMLTextAreaElement) => {
        const token = skillSlashTokenAt(textarea.value, textarea.selectionStart ?? textarea.value.length)
        if (!token || disabled || !onAddActiveSkill) {
          closeSkillMenu()
          return
        }
        setSkillToken(token)
        setSkillQuery(token.query)
        setHighlightedSkillIndex(0)
        setSkillMenuOpen(true)
      },
      [closeSkillMenu, disabled, onAddActiveSkill],
    )

    const selectSkill = useCallback(
      (skill: AgentRuntimeSkill) => {
        const textarea = textareaRef.current
        const token = skillToken ?? (textarea ? skillSlashTokenAt(value, textarea.selectionStart ?? value.length) : null)
        if (!token) return
        const nextValue = `${value.slice(0, token.start)}${value.slice(token.end)}`
        onChange(nextValue)
        onAddActiveSkill?.(skill.name)
        closeSkillMenu()
        window.requestAnimationFrame(() => {
          textarea?.focus()
          textarea?.setSelectionRange(token.start, token.start)
        })
      },
      [closeSkillMenu, onAddActiveSkill, onChange, skillToken, value],
    )

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
        {activeSkills.length ? (
          <div className="flex flex-wrap items-center gap-1.5 px-3" data-testid="agent-active-skills">
            <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground/70">
              {t("skills.activeForNextTurn")}
            </span>
            {activeSkills.map((skill) => (
              <button
                key={skill.name}
                type="button"
                className={cn(
                  composerSelectorChipClassName,
                  "max-w-[14rem] gap-1.5 px-2.5 text-foreground/78",
                )}
                onClick={() => onRemoveActiveSkill?.(skill.name)}
                disabled={disabled}
                aria-label={t("skills.remove", { name: skill.name })}
                data-testid="agent-active-skill-chip"
              >
                <span className="min-w-0 truncate">/{skill.name}</span>
                <X className="h-3 w-3 shrink-0 opacity-55" />
              </button>
            ))}
          </div>
        ) : null}
        <div className="relative">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(event) => {
              resizeTextarea(event.currentTarget)
              onChange(event.target.value)
              updateSkillMenu(event.currentTarget)
            }}
            onKeyDown={(event) => {
              if (event.nativeEvent.isComposing) return
              if (skillMenuOpen) {
                if (event.key === "ArrowDown") {
                  event.preventDefault()
                  setHighlightedSkillIndex((current) =>
                    skillOptions.length ? (current + 1) % skillOptions.length : 0,
                  )
                  return
                }
                if (event.key === "ArrowUp") {
                  event.preventDefault()
                  setHighlightedSkillIndex((current) =>
                    skillOptions.length
                      ? (current - 1 + skillOptions.length) % skillOptions.length
                      : 0,
                  )
                  return
                }
                if (event.key === "Escape") {
                  event.preventDefault()
                  closeSkillMenu()
                  return
                }
                if ((event.key === "Enter" || event.key === "Tab") && skillOptions[visibleHighlightedSkillIndex]) {
                  event.preventDefault()
                  selectSkill(skillOptions[visibleHighlightedSkillIndex])
                  return
                }
              }
              if (event.key === "Tab" && event.shiftKey && onModeChange) {
                event.preventDefault()
                onModeChange(mode === "plan" ? "execution" : "plan")
                return
              }
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault()
                onSubmit()
              }
            }}
            onClick={(event) => updateSkillMenu(event.currentTarget)}
            onBlur={() => window.setTimeout(closeSkillMenu, 120)}
            placeholder={t("composerPlaceholder")}
            aria-label={t("composerPlaceholder")}
            className={cn(
              "w-full resize-none bg-transparent px-3 py-2 text-[14px] leading-5 text-foreground outline-none placeholder:text-muted-foreground/64",
              isCenterPresentation ? "min-h-[64px]" : "min-h-10",
            )}
            rows={1}
            disabled={disabled}
            style={{ overflowY: "hidden" }}
          />
          {skillMenuOpen ? (
            <SkillSlashMenu
              skills={skillOptions}
              query={skillQuery}
              loading={skillsLoading}
              error={skillsError}
              highlightedIndex={visibleHighlightedSkillIndex}
              onHover={setHighlightedSkillIndex}
              onSelect={selectSkill}
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
              selectedConnectionId={selectedRemoteConnectionId}
              onSelectedConnectionChange={onRemoteConnectionChange}
            />
            {onPermissionModeChange ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className={cn(
                      composerSelectorChipClassName,
                      "hidden min-w-9 shrink items-center sm:inline-flex",
                      compactControls
                        ? "max-w-9 px-2"
                        : "max-w-[10rem] px-2",
                    )}
                    data-composer-chip="true"
                    disabled={disabled}
                    aria-label={t("permission.label")}
                  >
                    <PermissionIcon className={composerSelectorIconClassName} />
                    <span className={cn("min-w-0 truncate", compactControls && "sr-only")}>
                      {t(`permission.options.${permissionMode}.label`)}
                    </span>
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent
                  align="end"
                  side="top"
                  sideOffset={10}
                  className={cn("w-64", composerSelectorMenuClassName)}
                >
                  {permissionOptions.map(({ mode, Icon }) => (
                    <DropdownMenuItem
                      key={mode}
                      className="items-start gap-2 rounded-[7px] px-2 py-1.5 text-xs"
                      onSelect={() => onPermissionModeChange(mode)}
                    >
                      <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      <span className="grid gap-0.5">
                        <span className="font-medium text-foreground">
                          {t(`permission.options.${mode}.label`)}
                        </span>
                        <span className="text-[11px] leading-4 text-muted-foreground">
                          {t(`permission.options.${mode}.description`)}
                        </span>
                      </span>
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            ) : null}
            <AgentTokenUsageBadge
              summary={tokenUsageSummary}
              compact={compactControls}
            />
            {isRunning ? (
              <Button
                type="button"
                variant="outline"
                size="icon"
                className="ml-auto h-8 w-8 shrink-0 rounded-[10px] border-border/70 bg-card"
                onClick={onStop}
                aria-label={t("stop")}
              >
                <Square className="h-3.5 w-3.5" />
              </Button>
            ) : (
              <Button
                type="button"
                size="icon"
                className="ml-auto h-8 w-8 shrink-0 rounded-[10px] bg-primary text-primary-foreground shadow-none hover:bg-primary/88 focus-visible:ring-primary/25"
                onClick={onSubmit}
                disabled={!canSubmit}
                aria-label={t("send")}
              >
                <Send className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        </div>
      </div>
    )
  },
)

type SkillSlashToken = {
  start: number
  end: number
  query: string
}

function SkillSlashMenu({
  skills,
  query,
  loading,
  error,
  highlightedIndex,
  onHover,
  onSelect,
}: {
  skills: AgentRuntimeSkill[]
  query: string
  loading: boolean
  error?: string | null
  highlightedIndex: number
  onHover: (index: number) => void
  onSelect: (skill: AgentRuntimeSkill) => void
}) {
  const t = useTranslations("agentRuntime")
  const statusText = error
    ? t("skills.loadFailed")
    : loading
      ? t("skills.loading")
      : query
        ? t("skills.noMatches")
        : t("skills.empty")

  return (
    <div
      className={cn(
        "absolute bottom-[calc(100%+0.5rem)] left-3 z-50 w-[min(28rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-border bg-popover p-1.5 shadow-[0_18px_48px_rgba(36,35,33,0.12)]",
        composerSelectorMenuClassName,
      )}
      data-testid="agent-skill-menu"
    >
      <div className="px-2.5 py-1.5 text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground/70">
        {t("skills.menuTitle")}
      </div>
      {skills.length ? (
        <div className="grid gap-1">
          {skills.map((skill, index) => (
            <button
              key={skill.name}
              type="button"
              className={cn(
                "grid w-full gap-0.5 rounded-xl px-2.5 py-2 text-left transition-colors",
                index === highlightedIndex ? "bg-accent text-accent-foreground" : "hover:bg-accent/65",
              )}
              onMouseEnter={() => onHover(index)}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => onSelect(skill)}
              data-testid="agent-skill-option"
            >
              <span className="flex min-w-0 items-center gap-2 text-sm font-medium">
                <span className="min-w-0 truncate">/{skill.name}</span>
                <span className="shrink-0 text-[11px] text-muted-foreground">{skill.version}</span>
              </span>
              <span className="line-clamp-2 text-xs leading-5 text-muted-foreground">
                {skill.description}
              </span>
            </button>
          ))}
        </div>
      ) : (
        <div className="px-2.5 py-3 text-sm text-muted-foreground" data-testid="agent-skill-menu-empty">
          {statusText}
        </div>
      )}
    </div>
  )
}

function skillSlashTokenAt(value: string, cursor: number): SkillSlashToken | null {
  let start = cursor
  while (start > 0 && !/\s/.test(value[start - 1])) start -= 1
  const token = value.slice(start, cursor)
  if (!token.startsWith("/")) return null
  const query = token.slice(1)
  if (!/^[A-Za-z0-9._-]*$/.test(query)) return null
  return { start, end: cursor, query }
}

function skillMatchesQuery(skill: AgentRuntimeSkill, query: string) {
  const normalized = query.trim().toLowerCase()
  if (!normalized) return true
  return [skill.name, skill.description, skill.category, ...skill.tags]
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
      ? "border-[#FDEBEC] bg-[#FDEBEC]/70 text-[#9F2F2D]"
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
                      ? "bg-[#9F2F2D]"
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
