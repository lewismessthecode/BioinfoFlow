"use client"

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  type ComponentType,
  type CSSProperties,
  type KeyboardEvent,
  useMemo,
  useRef,
  useState,
} from "react"
import {
  CircleCheck,
  FileBox,
  FolderTree,
  Globe,
  MessageCircle,
  PanelRightClose,
  PanelRightOpen,
  RotateCcw,
  SlidersHorizontal,
  type AppIcon,
} from "@/lib/icons"
import { useTranslations } from "next-intl"

import { AgentComposer } from "./agent-composer"
import { AgentEnvironmentCard } from "./agent-environment-card"
import { AgentTabbedPanel, type AgentTabbedPanelTab } from "./agent-tabbed-panel"
import { AgentTodoDock } from "./agent-todo-dock"
import { AgentTranscript } from "./agent-transcript"
import { ComposerApprovalPopover } from "./composer-approval-popover"
import { todosFromArtifact } from "./artifact-viewers"
import { Button } from "@/components/ui/button"
import { ResizeHandle } from "@/components/ui/resize-handle"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useOptionalWorkspaceShell } from "@/components/bioinfoflow/workspace-shell-context"
import { useAgentRuntime } from "@/hooks/use-agent-runtime"
import { useLlmSettings } from "@/hooks/use-llm-settings"
import { useIsMobile } from "@/hooks/use-media-query"
import {
  buildAgentRuntimeTimeline,
  deriveTodoDisplayItems,
  listAgentRuntimeSessionArtifacts,
  listAgentRuntimeSkills,
  type AgentRuntimeArtifact,
  type AgentRuntimeFileRefPart,
  type AgentRuntimeInputPart,
  type AgentRuntimeSkill,
  type AgentModelSelection,
  type AgentRuntimeTurn,
} from "@/lib/agent-runtime"
import {
  readAgentTurnPolicy,
  type AgentTurnPolicy,
} from "@/lib/agent-runtime/turn-policy"
import { cn } from "@/lib/utils"

const ACTIVE_TURN_STATUSES = new Set<AgentRuntimeTurn["status"]>([
  "queued",
  "running",
  "waiting_user",
  "waiting_approval",
])
const SIDECAR_WIDTH_STORAGE_KEY = "agent-sidecar-width"
const SIDECAR_MIN_WIDTH = 380
const SIDECAR_DEFAULT_WIDTH = 600
const SIDECAR_MAX_WIDTH = 760
const SIDECAR_MAIN_MIN_WIDTH = 420

const STARTER_SUGGESTIONS = [
  {
    key: "checkWorkflow",
    icon: MessageCircle,
  },
  {
    key: "chooseInputs",
    icon: MessageCircle,
  },
  {
    key: "reviewFailure",
    icon: RotateCcw,
  },
  {
    key: "prepareRun",
    icon: CircleCheck,
  },
] as const

const COMMAND_DISCOVERY_HINTS = [
  { key: "workflow", token: "@workflow" },
  { key: "skills", token: "/" },
  { key: "mode", token: "Shift+Tab" },
] as const

const WORKFLOW_MENTION_PATTERN = /(^|\s)@workflow(?=\s|$|[,.!?;:])/gi

const SIDECAR_TABS: Array<{
  key: AgentTabbedPanelTab
  labelKey: string
  iconName: string
  Icon: AppIcon
}> = [
  { key: "preview", labelKey: "tabs.artifacts", iconName: "file-box", Icon: FileBox },
  { key: "files", labelKey: "tabs.files", iconName: "folder-tree", Icon: FolderTree },
  { key: "browser", labelKey: "tabs.browser", iconName: "globe", Icon: Globe },
]

type PendingSubmission = {
  text: string
  inputParts: AgentRuntimeInputPart[]
  activeSkillNames: string[]
  modelSelection: AgentModelSelection | null
  optimisticTurn: AgentRuntimeTurn
  sessionId: string
}

export type AgentWorkbenchHandle = {
  focusInput: () => void
  stop: () => void
  newConversation: () => void
}

type AgentWorkbenchProps = {
  projectId?: string | null
  activeSessionId?: string | null
  onActiveSessionIdChange?: (sessionId: string) => void
  workspaceEnabled?: boolean
  className?: string
}

export const AgentWorkbench = forwardRef<AgentWorkbenchHandle, AgentWorkbenchProps>(
  function AgentWorkbench(
    {
      projectId,
      activeSessionId,
      onActiveSessionIdChange,
      workspaceEnabled = true,
      className,
    },
    ref,
  ) {
    const t = useTranslations("agentRuntime")
    const textareaRef = useRef<HTMLTextAreaElement>(null)
    const mobileSidecarDialogRef = useRef<HTMLDivElement>(null)
    const mobileSidecarRestoreFocusRef = useRef<HTMLElement | null>(null)
    const desktopSidecarFocusTargetRef = useRef<"navbar" | null>(null)
    const environmentPanelRef = useRef<HTMLDivElement>(null)
    const composerShellRef = useRef<HTMLDivElement>(null)
    const workbenchRootRef = useRef<HTMLDivElement>(null)
    const isMobile = useIsMobile()
    const [input, setInput] = useState("")
    const [contextAttachments, setContextAttachments] = useState<AgentRuntimeFileRefPart[]>([])
    const [availableSkills, setAvailableSkills] = useState<AgentRuntimeSkill[]>([])
    const [activeSkillNames, setActiveSkillNames] = useState<string[]>([])
    const [skillsLoading, setSkillsLoading] = useState(true)
    const [skillsError, setSkillsError] = useState<string | null>(null)
    const [remoteConnectionOverride, setRemoteConnectionOverride] = useState<{
      sessionId: string
      value: string
    } | null>(null)
    const [hasSubmittedDraft, setHasSubmittedDraft] = useState(false)
    const [optimisticTurns, setOptimisticTurns] = useState<AgentRuntimeTurn[]>([])
    const [inFlightOptimisticTurnIds, setInFlightOptimisticTurnIds] = useState<
      string[]
    >([])
    const [turnPolicy] = useState<AgentTurnPolicy>(readAgentTurnPolicy)
    const [queuedSubmissions, setQueuedSubmissions] = useState<PendingSubmission[]>([])
    const [pendingInterruptSubmission, setPendingInterruptSubmission] =
      useState<PendingSubmission | null>(null)
    const [environmentOpen, setEnvironmentOpen] = useState(false)
    const [sidecarOpen, setSidecarOpen] = useState(false)
    const [sidecarMaxWidth, setSidecarMaxWidth] = useState(SIDECAR_MAX_WIDTH)
    const [sidecarWidth, setSidecarWidth] = useState(() => {
      if (typeof window === "undefined") return SIDECAR_DEFAULT_WIDTH
      const storedValue = window.localStorage.getItem(SIDECAR_WIDTH_STORAGE_KEY)
      if (!storedValue) return SIDECAR_DEFAULT_WIDTH
      const storedWidth = Number(storedValue)
      return Number.isFinite(storedWidth)
        ? clampSidecarWidth(storedWidth)
        : SIDECAR_DEFAULT_WIDTH
    })
    const [activeSidecarTab, setActiveSidecarTab] = useState<AgentTabbedPanelTab>("preview")
    const [composerBottomSpace, setComposerBottomSpace] = useState(176)
    const [browserInput, setBrowserInput] = useState("")
    const [browserSrc, setBrowserSrc] = useState("")
    const [artifactState, setArtifactState] = useState<{
      sessionId: string
      artifacts: AgentRuntimeArtifact[]
    } | null>(null)
    const workspaceShell = useOptionalWorkspaceShell()
    const setNavbarActions = workspaceShell?.setNavbarActions
    const { models, selectedModel, isLoading: modelsLoading, setSelectedModel } =
      useLlmSettings()
    const {
      state,
      eventWindowLimited,
      mode,
      setMode,
      permissionMode,
      setPermissionMode,
      setActiveSessionId,
      send,
      interrupt,
      decideAction,
    } = useAgentRuntime(projectId, {
      activeSessionId,
      onActiveSessionIdChange,
    })
    const agentMode = mode ?? "execution"
    const sessionId = state.session?.id ?? ""
    const submissionSessionId = activeSessionId || sessionId || "pending-session"
    const sessionRemoteConnectionId = getSessionRemoteConnectionId(state.session?.metadata)
    const projectRemoteConnectionId = useMemo(() => {
      if (!projectId) return ""
      const project = workspaceShell?.projects.find((item) => item.id === projectId)
      if (project?.storage_mode !== "remote") return ""
      return typeof project.remote_connection_id === "string"
        ? project.remote_connection_id
        : ""
    }, [projectId, workspaceShell?.projects])
    const hasRemoteConnectionOverride =
      remoteConnectionOverride?.sessionId === sessionId
    const selectedRemoteConnectionId =
      hasRemoteConnectionOverride
        ? remoteConnectionOverride.value
        : sessionRemoteConnectionId || (state.session ? "" : projectRemoteConnectionId)

    const disabled = !workspaceEnabled
    const visibleOptimisticTurns = optimisticTurns.filter(
      (optimisticTurn) =>
        !state.turns.some((turn) => turn.id === optimisticTurn.id),
    )
    const transcriptTimeline = useMemo(
      () =>
        visibleOptimisticTurns.length
          ? buildAgentRuntimeTimeline(
              [...state.turns, ...visibleOptimisticTurns],
              state.events,
            )
          : state.timeline,
      [state.events, state.timeline, state.turns, visibleOptimisticTurns],
    )
    const hasTurns = state.turns.length > 0 || visibleOptimisticTurns.length > 0
    const hasSelectedSession = Boolean(activeSessionId || state.session?.id)
    const hasConversation = hasTurns || hasSubmittedDraft || hasSelectedSession
    const isRunning = state.status === "running"
    const hasInterruptibleBackendTurn = state.turns.some((turn) =>
      ACTIVE_TURN_STATUSES.has(turn.status),
    )
    const hasActiveTurn =
      isRunning ||
      hasInterruptibleBackendTurn ||
      visibleOptimisticTurns.some((turn) =>
        inFlightOptimisticTurnIds.includes(turn.id),
      )
    const artifactEventCount = useMemo(
      () => state.events.filter((event) => event.type === "artifact.created").length,
      [state.events],
    )
    const transcriptArtifacts = useMemo(
      () =>
        artifactState && artifactState.sessionId === state.session?.id
          ? artifactState.artifacts
          : [],
      [artifactState, state.session?.id],
    )
    const latestTurnId = state.timeline.at(-1)?.turn.id ?? null
    const latestTodoArtifact = useMemo(() => {
      if (!latestTurnId) return undefined
      return [...transcriptArtifacts]
        .filter((artifact) => artifact.type === "todo_list" && artifact.turn_id === latestTurnId)
        .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))[0]
    }, [latestTurnId, transcriptArtifacts])
    const todoTurn = latestTodoArtifact
      ? state.timeline.find((entry) => entry.turn.id === latestTodoArtifact.turn_id)?.turn ?? null
      : null
    const todoDisplayItems = useMemo(
      () =>
        latestTodoArtifact
          ? deriveTodoDisplayItems(todosFromArtifact(latestTodoArtifact), todoTurn)
          : [],
      [latestTodoArtifact, todoTurn],
    )
    // The side panel is now secondary detail. Approvals surface inline and above
    // the composer, so pending decisions no longer force the drawer open.
    const desktopSidecarVisible = sidecarOpen && !isMobile

    useEffect(() => {
      const updateSidecarConstraints = () => {
        const rootWidth = workbenchRootRef.current?.getBoundingClientRect().width ?? 0
        const nextMaxWidth = maxSidecarWidthForWorkbench(rootWidth)
        setSidecarMaxWidth((current) =>
          current === nextMaxWidth ? current : nextMaxWidth,
        )
      }

      updateSidecarConstraints()
      window.addEventListener("resize", updateSidecarConstraints)

      if (typeof ResizeObserver === "undefined") {
        return () => window.removeEventListener("resize", updateSidecarConstraints)
      }

      const resizeObserver = new ResizeObserver(updateSidecarConstraints)
      const root = workbenchRootRef.current
      if (root) resizeObserver.observe(root)

      return () => {
        window.removeEventListener("resize", updateSidecarConstraints)
        resizeObserver.disconnect()
      }
    }, [])

    useEffect(() => {
      window.localStorage.setItem(SIDECAR_WIDTH_STORAGE_KEY, String(sidecarWidth))
    }, [sidecarWidth])

    useEffect(() => {
      if (!hasConversation) return
      const shell = composerShellRef.current
      if (!shell) return

      const updateBottomSpace = () => {
        const next = Math.max(160, Math.ceil(shell.getBoundingClientRect().height + 24))
        setComposerBottomSpace((current) => (Math.abs(current - next) > 1 ? next : current))
      }

      updateBottomSpace()
      if (typeof ResizeObserver === "undefined") return

      const resizeObserver = new ResizeObserver(updateBottomSpace)
      resizeObserver.observe(shell)
      return () => resizeObserver.disconnect()
    }, [hasConversation])
    const mobileSidecarVisible = sidecarOpen && isMobile
    const sidecarLabel = desktopSidecarVisible || mobileSidecarVisible
      ? t("sidecar.collapse")
      : t("sidecar.expand")
    const environmentLabel = environmentOpen
      ? t("environment.close")
      : t("environment.open")
    const skillsLoadFailedLabel = t("skills.loadFailed")

    const clearLocalPendingSubmissions = useCallback(() => {
      setQueuedSubmissions([])
      setPendingInterruptSubmission(null)
      setOptimisticTurns((current) =>
        current.filter((turn) => !isLocalPendingSubmissionTurn(turn)),
      )
    }, [])

    const stopCurrentTurn = useCallback(() => {
      clearLocalPendingSubmissions()
      void interrupt()
    }, [clearLocalPendingSubmissions, interrupt])

    useImperativeHandle(
      ref,
      () => ({
        focusInput: () => textareaRef.current?.focus(),
        stop: stopCurrentTurn,
        newConversation: () => {
          setActiveSessionId(null)
          setInput("")
          setContextAttachments([])
          setActiveSkillNames([])
          setRemoteConnectionOverride(null)
          setHasSubmittedDraft(false)
          setOptimisticTurns([])
          setInFlightOptimisticTurnIds([])
          setQueuedSubmissions([])
          setPendingInterruptSubmission(null)
          setEnvironmentOpen(false)
          setSidecarOpen(false)
          setActiveSidecarTab("preview")
          setBrowserInput("")
          setBrowserSrc("")
        },
      }),
      [setActiveSessionId, stopCurrentTurn],
    )

    useEffect(() => {
      let cancelled = false
      void listAgentRuntimeSkills()
        .then((skills) => {
          if (!cancelled) setAvailableSkills(skills)
        })
        .catch((error) => {
          if (!cancelled) {
            setAvailableSkills([])
            setSkillsError(error instanceof Error ? error.message : skillsLoadFailedLabel)
          }
        })
        .finally(() => {
          if (!cancelled) setSkillsLoading(false)
        })
      return () => {
        cancelled = true
      }
    }, [skillsLoadFailedLabel])

    useEffect(() => {
      const sessionId = state.session?.id
      if (!sessionId) return
      let cancelled = false
      void listAgentRuntimeSessionArtifacts(sessionId)
        .then((next) => {
          if (!cancelled) setArtifactState({ sessionId, artifacts: next })
        })
        .catch(() => {
          if (!cancelled) setArtifactState({ sessionId, artifacts: [] })
        })
      return () => {
        cancelled = true
      }
    }, [state.session?.id, artifactEventCount])

    useEffect(() => {
      if (submissionSessionId === "pending-session") return
      const timer = window.setTimeout(() => {
        setQueuedSubmissions((current) =>
          current
            .filter((submission) =>
              submission.sessionId === submissionSessionId ||
              submission.sessionId === "pending-session",
            )
            .map((submission) =>
              submission.sessionId === "pending-session"
                ? reassignPendingSubmission(submission, submissionSessionId)
                : submission,
            ),
        )
        setPendingInterruptSubmission((current) => {
          if (!current) return current
          if (current.sessionId === submissionSessionId) return current
          if (current.sessionId === "pending-session") {
            return reassignPendingSubmission(current, submissionSessionId)
          }
          return null
        })
        setOptimisticTurns((current) =>
          current
            .filter((turn) => {
              if (!isLocalPendingSubmissionTurn(turn)) return true
              return (
                turn.session_id === submissionSessionId ||
                turn.session_id === "pending-session"
              )
            })
            .map((turn) =>
              isLocalPendingSubmissionTurn(turn) &&
              turn.session_id === "pending-session"
                ? { ...turn, session_id: submissionSessionId }
                : turn,
            ),
        )
      }, 0)
      return () => window.clearTimeout(timer)
    }, [submissionSessionId])

    const addContextAttachment = useCallback((path: string) => {
      const label = path.split("/").pop() || path
      setContextAttachments((current) => {
        if (current.some((attachment) => attachment.path === path)) return current
        return [...current, { kind: "file_ref", path, label, includeContent: true }]
      })
    }, [])

    const removeContextAttachment = useCallback((path: string) => {
      setContextAttachments((current) =>
        current.filter((attachment) => attachment.path !== path),
      )
    }, [])

    const addActiveSkill = useCallback((name: string) => {
      setActiveSkillNames((current) =>
        current.includes(name) ? current : [...current, name],
      )
    }, [])

    const removeActiveSkill = useCallback((name: string) => {
      setActiveSkillNames((current) => current.filter((item) => item !== name))
    }, [])

    const fillStarterSuggestion = useCallback((prompt: string) => {
      setInput(prompt)
      window.requestAnimationFrame(() => {
        textareaRef.current?.focus()
        textareaRef.current?.setSelectionRange(prompt.length, prompt.length)
      })
    }, [])

    const handleRemoteConnectionChange = useCallback(
      (connectionId: string) => {
        setRemoteConnectionOverride({ sessionId, value: connectionId })
      },
      [sessionId],
    )

    const sendTurn = useCallback(
      (
        text: string,
        inputParts: AgentRuntimeInputPart[],
        activeSkillNamesSnapshot: string[],
        modelSelection = selectedModel,
        optimisticTurnOverride?: AgentRuntimeTurn,
      ) => {
        const trimmedText = text.trim()
        if (!trimmedText) return
        setHasSubmittedDraft(true)
        const nextOptimisticTurn =
          optimisticTurnOverride ??
          createOptimisticTurn({
            text: trimmedText,
            inputParts,
            activeSkillNames: activeSkillNamesSnapshot,
            sessionId: submissionSessionId,
            projectId,
          })
        setOptimisticTurns((current) => {
          if (current.some((turn) => turn.id === nextOptimisticTurn.id)) {
            return current
          }
          return [...current, nextOptimisticTurn]
        })
        setInFlightOptimisticTurnIds((current) => {
          if (current.includes(nextOptimisticTurn.id)) return current
          return [...current, nextOptimisticTurn.id]
        })
        void send(trimmedText, {
          modelSelection,
          inputParts,
          activeSkillNames: activeSkillNamesSnapshot,
          ...(hasRemoteConnectionOverride || selectedRemoteConnectionId || state.session
            ? { remoteConnectionId: selectedRemoteConnectionId }
            : {}),
        }).then(() => {
          setOptimisticTurns((current) =>
            current.filter((turn) => turn.id !== nextOptimisticTurn.id),
          )
          setInFlightOptimisticTurnIds((current) =>
            current.filter((id) => id !== nextOptimisticTurn.id),
          )
        })
      },
      [
        hasRemoteConnectionOverride,
        projectId,
        selectedModel,
        selectedRemoteConnectionId,
        send,
        submissionSessionId,
        state.session,
      ],
    )

    const submitTurn = useCallback(
      (
        text: string,
        inputParts: AgentRuntimeInputPart[],
        activeSkillNamesSnapshot: string[],
        modelSelection = selectedModel,
      ) => {
        const trimmedText = text.trim()
        if (!trimmedText) return
        if (!hasActiveTurn) {
          sendTurn(trimmedText, inputParts, activeSkillNamesSnapshot, modelSelection)
          return
        }

        if (turnPolicy === "queue") {
          const nextOptimisticTurn = createOptimisticTurn({
            text: trimmedText,
            inputParts,
            activeSkillNames: activeSkillNamesSnapshot,
            sessionId: submissionSessionId,
            projectId,
            localQueue: true,
          })
          setHasSubmittedDraft(true)
          setOptimisticTurns((current) => [...current, nextOptimisticTurn])
          setQueuedSubmissions((current) => [
            ...current,
            {
              text: trimmedText,
              inputParts,
              activeSkillNames: activeSkillNamesSnapshot,
              modelSelection,
              optimisticTurn: nextOptimisticTurn,
              sessionId: submissionSessionId,
            },
          ])
          return
        }

        if (!hasInterruptibleBackendTurn) {
          const nextOptimisticTurn = createOptimisticTurn({
            text: trimmedText,
            inputParts,
            activeSkillNames: activeSkillNamesSnapshot,
            sessionId: submissionSessionId,
            projectId,
            localPendingInterrupt: true,
          })
          setHasSubmittedDraft(true)
          setOptimisticTurns((current) => [
            ...current.filter(
              (turn) => turn.loop_state?.local_pending_interrupt !== true,
            ),
            nextOptimisticTurn,
          ])
          setPendingInterruptSubmission({
            text: trimmedText,
            inputParts,
            activeSkillNames: activeSkillNamesSnapshot,
            modelSelection,
            optimisticTurn: nextOptimisticTurn,
            sessionId: submissionSessionId,
          })
          return
        }

        void (async () => {
          await interrupt()
          sendTurn(trimmedText, inputParts, activeSkillNamesSnapshot, modelSelection)
        })()
      },
      [
        hasActiveTurn,
        hasInterruptibleBackendTurn,
        interrupt,
        projectId,
        selectedModel,
        sendTurn,
        submissionSessionId,
        turnPolicy,
      ],
    )

    useEffect(() => {
      if (!queuedSubmissions.length || hasActiveTurn) return
      const next = queuedSubmissions[0]
      if (next.sessionId !== submissionSessionId) {
        const timer = window.setTimeout(() => {
          setQueuedSubmissions((current) =>
            current[0] === next ? current.slice(1) : current,
          )
          setOptimisticTurns((current) =>
            current.filter((turn) => turn.id !== next.optimisticTurn.id),
          )
        }, 0)
        return () => window.clearTimeout(timer)
      }
      const timer = window.setTimeout(() => {
        setQueuedSubmissions((current) =>
          current[0] === next ? current.slice(1) : current,
        )
        sendTurn(next.text, next.inputParts, next.activeSkillNames, next.modelSelection, next.optimisticTurn)
      }, 0)
      return () => window.clearTimeout(timer)
    }, [hasActiveTurn, queuedSubmissions, sendTurn, submissionSessionId])

    useEffect(() => {
      if (!pendingInterruptSubmission) return
      const next = pendingInterruptSubmission
      if (next.sessionId !== submissionSessionId) {
        const timer = window.setTimeout(() => {
          setPendingInterruptSubmission((current) =>
            current === next ? null : current,
          )
          setOptimisticTurns((current) =>
            current.filter((turn) => turn.id !== next.optimisticTurn.id),
          )
        }, 0)
        return () => window.clearTimeout(timer)
      }
      if (hasActiveTurn && !hasInterruptibleBackendTurn) return
      const timer = window.setTimeout(() => {
        setPendingInterruptSubmission((current) => (current === next ? null : current))
        void (async () => {
          if (hasInterruptibleBackendTurn) await interrupt()
          sendTurn(next.text, next.inputParts, next.activeSkillNames, next.modelSelection, next.optimisticTurn)
        })()
      }, 0)
      return () => window.clearTimeout(timer)
    }, [
      hasActiveTurn,
      hasInterruptibleBackendTurn,
      interrupt,
      pendingInterruptSubmission,
      sendTurn,
      submissionSessionId,
    ])

    const submit = () => {
      const workflowInput = workflowContextInputFromComposerValue({
        value: input,
        projectId,
        label: t("workflowContext.label"),
      })
      const text = workflowInput.text
      if (!text) return
      const inputParts: AgentRuntimeInputPart[] = [
        { type: "text", text },
        ...workflowInput.workflowParts,
        ...contextAttachments,
      ]
      const activeSkillNamesSnapshot = [...activeSkillNames]
      submitTurn(text, inputParts, activeSkillNamesSnapshot, selectedModel)
      setInput("")
      setContextAttachments([])
      setActiveSkillNames([])
    }

    const retryTurn = useCallback(
      (turn: AgentRuntimeTurn) => {
        const text = turn.input_text.trim()
        if (!text) return
        const inputParts =
          turn.input_parts && turn.input_parts.length
            ? turn.input_parts
            : [{ type: "text" as const, text }]
        submitTurn(text, inputParts, turn.active_skill_names ?? [], turn.model_selection ?? null)
      },
      [submitTurn],
    )

    const focusNavbarSidecarToggle = useCallback(() => {
      let attempts = 0
      const tryFocus = () => {
        const target = document.querySelector<HTMLElement>(
          '[data-agent-workbench-action="sidecar-toggle"]',
        )
        if (target) {
          target.focus()
          return
        }
        attempts += 1
        if (attempts < 10) {
          window.setTimeout(tryFocus, 16)
        }
      }
      window.setTimeout(tryFocus, 0)
    }, [])

    const closeSidecar = useCallback((focusTarget?: "navbar") => {
      if (focusTarget) {
        desktopSidecarFocusTargetRef.current = focusTarget
      }
      setSidecarOpen(false)
    }, [])

    useEffect(() => {
      if (desktopSidecarVisible || mobileSidecarVisible) return
      if (desktopSidecarFocusTargetRef.current !== "navbar") return
      desktopSidecarFocusTargetRef.current = null
      focusNavbarSidecarToggle()
    }, [desktopSidecarVisible, focusNavbarSidecarToggle, mobileSidecarVisible])

    useEffect(() => {
      if (!environmentOpen || desktopSidecarVisible) return
      window.requestAnimationFrame(() => {
        environmentPanelRef.current?.focus()
      })
    }, [desktopSidecarVisible, environmentOpen])

    useEffect(() => {
      if (!mobileSidecarVisible) return
      mobileSidecarRestoreFocusRef.current =
        document.activeElement instanceof HTMLElement ? document.activeElement : null
      window.requestAnimationFrame(() => mobileSidecarDialogRef.current?.focus())
      return () => {
        const restoreTarget = mobileSidecarRestoreFocusRef.current
        if (restoreTarget?.isConnected) restoreTarget.focus()
        mobileSidecarRestoreFocusRef.current = null
      }
    }, [mobileSidecarVisible])

    const onMobileSidecarKeyDown = useCallback(
      (event: KeyboardEvent<HTMLDivElement>) => {
        if (event.key === "Escape") {
          closeSidecar()
          return
        }
        if (event.key !== "Tab") return

        const focusable = Array.from(
          event.currentTarget.querySelectorAll<HTMLElement>(
            [
              "a[href]",
              "button:not([disabled])",
              "textarea:not([disabled])",
              "input:not([disabled])",
              "select:not([disabled])",
              "[tabindex]:not([tabindex='-1'])",
            ].join(","),
          ),
        ).filter((element) => element.offsetParent !== null || element === event.currentTarget)

        if (!focusable.length) {
          event.preventDefault()
          event.currentTarget.focus()
          return
        }

        const first = focusable[0]
        const last = focusable.at(-1) ?? first
        const activeElement = document.activeElement
        if (event.shiftKey && (activeElement === first || activeElement === event.currentTarget)) {
          event.preventDefault()
          last.focus()
        } else if (!event.shiftKey && activeElement === last) {
          event.preventDefault()
          first.focus()
        }
      },
      [closeSidecar],
    )

    const toggleSidecar = useCallback(() => {
      if (desktopSidecarVisible || mobileSidecarVisible) {
        closeSidecar(desktopSidecarVisible ? "navbar" : undefined)
        return
      }
      setEnvironmentOpen(false)
      setSidecarOpen(true)
    }, [closeSidecar, desktopSidecarVisible, mobileSidecarVisible])

    const toggleEnvironment = useCallback(() => {
      setEnvironmentOpen((current) => {
        const next = !current
        if (next) {
          setSidecarOpen(false)
        }
        return next
      })
    }, [])

    const resizeSidecar = useCallback((delta: number) => {
      setSidecarWidth((current) => {
        const visibleWidth = clampSidecarWidth(current, sidecarMaxWidth)
        return clampSidecarWidth(visibleWidth + delta, sidecarMaxWidth)
      })
    }, [sidecarMaxWidth])

    const onSidecarTabKeyDown = useCallback(
      (event: KeyboardEvent<HTMLButtonElement>, currentIndex: number) => {
        const lastIndex = SIDECAR_TABS.length - 1
        let nextIndex: number | null = null
        switch (event.key) {
          case "ArrowRight":
          case "ArrowDown":
            nextIndex = currentIndex === lastIndex ? 0 : currentIndex + 1
            break
          case "ArrowLeft":
          case "ArrowUp":
            nextIndex = currentIndex === 0 ? lastIndex : currentIndex - 1
            break
          case "Home":
            nextIndex = 0
            break
          case "End":
            nextIndex = lastIndex
            break
          default:
            break
        }
        if (nextIndex === null) return
        event.preventDefault()
        const nextTab = SIDECAR_TABS[nextIndex]?.key
        if (!nextTab) return
        setActiveSidecarTab(nextTab)
        window.requestAnimationFrame(() => {
          document.getElementById(`agent-sidecar-tab-${nextTab}`)?.focus()
        })
      },
      [],
    )

    const agentActionButtons = useMemo(
      () => (
        <>
          {desktopSidecarVisible ? (
            <div
              className="mr-1 flex min-w-0 items-center gap-1 border-r border-border/55 pr-1.5"
              role="tablist"
              aria-label={t("sidecar.title")}
              data-testid="agent-sidecar-tab-strip"
            >
              {SIDECAR_TABS.map(({ key, labelKey, iconName, Icon }, index) => (
                <Tooltip key={key}>
                  <TooltipTrigger asChild>
                    <button
                      type="button"
                      role="tab"
                      id={`agent-sidecar-tab-${key}`}
                      aria-controls={`agent-sidecar-panel-${key}`}
                      aria-selected={activeSidecarTab === key}
                      tabIndex={activeSidecarTab === key ? 0 : -1}
                      onClick={() => setActiveSidecarTab(key)}
                      onKeyDown={(event) => onSidecarTabKeyDown(event, index)}
                      aria-label={t(labelKey)}
                      className={cn(
                        "flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] text-muted-foreground transition-colors hover:bg-muted/45 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25 focus-visible:ring-offset-1 focus-visible:ring-offset-background",
                        activeSidecarTab === key && "bg-muted/60 text-foreground",
                      )}
                      data-active={activeSidecarTab === key}
                    >
                      <Icon
                        className="h-4 w-4 shrink-0"
                        data-icon={iconName}
                        data-testid={`agent-sidecar-tab-icon-${key}`}
                        aria-hidden="true"
                      />
                    </button>
                  </TooltipTrigger>
                  <TooltipContent side="bottom">{t(labelKey)}</TooltipContent>
                </Tooltip>
              ))}
            </div>
          ) : null}
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className={cn(
              "h-8 w-8 rounded-[8px] border border-transparent text-foreground/78 transition-colors hover:bg-accent hover:text-foreground",
              environmentOpen && "bg-accent text-foreground",
            )}
            onClick={toggleEnvironment}
            aria-label={environmentLabel}
            data-agent-workbench-action="environment"
          >
            <SlidersHorizontal className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 rounded-[8px] border border-transparent text-foreground/78 transition-colors hover:bg-accent hover:text-foreground"
            onClick={toggleSidecar}
            aria-label={sidecarLabel}
            data-agent-workbench-action="sidecar-toggle"
          >
            {desktopSidecarVisible || mobileSidecarVisible ? (
              <PanelRightClose className="h-4 w-4" />
            ) : (
              <PanelRightOpen className="h-4 w-4" />
            )}
          </Button>
        </>
      ),
      [
        activeSidecarTab,
        desktopSidecarVisible,
        environmentLabel,
        environmentOpen,
        mobileSidecarVisible,
        onSidecarTabKeyDown,
        sidecarLabel,
        t,
        toggleEnvironment,
        toggleSidecar,
      ],
    )

    useEffect(() => {
      if (!setNavbarActions) return

      setNavbarActions(agentActionButtons)

      return () => setNavbarActions(null)
    }, [agentActionButtons, setNavbarActions])

    const composerDocked = hasConversation
    const composer = (
      <AgentComposer
        ref={textareaRef}
        value={input}
        onChange={setInput}
        onSubmit={submit}
        onStop={stopCurrentTurn}
        isRunning={isRunning}
        disabled={disabled}
        mode={agentMode}
        onModeChange={setMode ? (next) => void setMode(next) : undefined}
        permissionMode={permissionMode}
        onPermissionModeChange={
          setPermissionMode ? (next) => void setPermissionMode(next) : undefined
        }
        models={models}
        selectedModel={selectedModel}
        modelsLoading={modelsLoading}
        onSelectModel={(model) => void setSelectedModel(model)}
        contextAttachments={contextAttachments}
        onRemoveContextAttachment={removeContextAttachment}
        availableSkills={availableSkills}
        activeSkillNames={activeSkillNames}
        skillsLoading={skillsLoading}
        skillsError={skillsError}
        onAddActiveSkill={addActiveSkill}
        onRemoveActiveSkill={removeActiveSkill}
        tokenUsageSummary={state.session?.token_usage_summary}
        selectedRemoteConnectionId={selectedRemoteConnectionId}
        onRemoteConnectionChange={handleRemoteConnectionChange}
        compactControls={desktopSidecarVisible}
        presentation={composerDocked ? "dock" : "center"}
        contextTitle={null}
      />
    )

    const constrainedSidecarWidth = desktopSidecarVisible
      ? clampSidecarWidth(sidecarWidth, sidecarMaxWidth)
      : 0
    const sidecarResizeMax = Math.min(Math.max(sidecarMaxWidth, 0), SIDECAR_MAX_WIDTH)
    const sidecarResizeMin = sidecarResizeMax > 0
      ? Math.min(SIDECAR_MIN_WIDTH, sidecarResizeMax)
      : 0

    return (
      <div
        ref={workbenchRootRef}
        className={cn("relative flex h-full min-w-0 flex-1 bg-background", className)}
        data-testid="agent-workbench-root"
      >
        <main
          className="relative flex min-w-0 flex-1 flex-col overflow-hidden transition-[padding,width] duration-300 ease-out"
          data-testid="agent-workbench-main"
          style={
            composerDocked
              ? ({
                  "--agent-composer-bottom-space": `${composerBottomSpace}px`,
                } as CSSProperties)
              : undefined
          }
        >
          {hasConversation ? (
            <>
              <AgentTodoDock items={todoDisplayItems} />
              <AgentTranscript
                timeline={transcriptTimeline}
                onDecision={decideAction}
                onRetryTurn={retryTurn}
                eventWindowLimited={eventWindowLimited}
              />
            </>
          ) : (
            <div
              className={cn(
                "agent-halo-surface flex min-h-0 flex-1 items-center justify-center px-4 py-8",
                composerDocked && "items-start pt-[22vh]",
              )}
            >
              <div
                className={cn(
                  "agent-center-stage relative w-full",
                  composerDocked ? "max-w-[36rem]" : "max-w-[42rem] -translate-y-8",
                )}
              >
                <h1 className="mb-4 text-center text-[15px] font-medium tracking-normal text-muted-foreground">
                  {t("welcomeTitle")}
                </h1>
                {!composerDocked ? (
                  <div data-testid="agent-composer-shell" data-placement="center">
                    {composer}
                  </div>
                ) : null}
                {!composerDocked && !input.trim() ? (
                  <StarterSuggestionList
                    suggestions={STARTER_SUGGESTIONS.slice(
                      0,
                      desktopSidecarVisible ? 3 : STARTER_SUGGESTIONS.length,
                    ).map((suggestion) => ({
                      key: suggestion.key,
                      icon: suggestion.icon,
                      prompt: t(`starterSuggestions.${suggestion.key}.prompt`),
                    }))}
                    onSelect={fillStarterSuggestion}
                  />
                ) : null}
              </div>
              {!input.trim() ? (
                <CommandDiscoveryHints
                  hints={COMMAND_DISCOVERY_HINTS.map((hint) => ({
                    key: hint.key,
                    token: hint.token,
                    prefix: t(`commandHints.${hint.key}.prefix`),
                    suffix: t(`commandHints.${hint.key}.suffix`),
                  }))}
                />
              ) : null}
            </div>
          )}

          {composerDocked ? (
            <div
              ref={composerShellRef}
              className="pointer-events-none absolute inset-x-0 bottom-0 z-20 px-3 pb-4 pt-10 sm:px-6"
              data-testid="agent-composer-shell"
              data-placement="bottom"
            >
              <div className="pointer-events-auto">
                <ComposerApprovalPopover events={state.events} />
                {composer}
              </div>
            </div>
          ) : null}

          {state.error ? (
            <div className="absolute inset-x-4 bottom-24 mx-auto max-w-3xl rounded-2xl border border-destructive/25 bg-destructive/5 px-4 py-3 text-sm text-destructive shadow-sm sm:bottom-28">
              {state.error}
            </div>
          ) : null}

          {environmentOpen && !desktopSidecarVisible ? (
            <div
              ref={environmentPanelRef}
              className="pointer-events-auto absolute right-3 top-3 z-20 w-[min(440px,calc(100%-1.5rem))] sm:right-5 sm:top-5"
              data-testid="agent-environment-floating-panel"
              tabIndex={-1}
            >
              <AgentEnvironmentCard
                projectId={projectId}
                session={state.session}
                events={state.events}
                artifacts={transcriptArtifacts}
              />
            </div>
          ) : null}
        </main>

        <div
          className={cn(
            "relative hidden shrink-0 overflow-hidden transition-[width,opacity,transform] duration-300 ease-out lg:flex",
            desktopSidecarVisible
              ? "translate-x-0 opacity-100"
              : "pointer-events-none translate-x-4 opacity-0",
          )}
          style={{
            width: constrainedSidecarWidth,
            maxWidth: desktopSidecarVisible
              ? `calc(100% - ${SIDECAR_MAIN_MIN_WIDTH}px)`
              : undefined,
          }}
          aria-hidden={!desktopSidecarVisible}
          data-testid="agent-sidecar-column"
        >
          {desktopSidecarVisible ? (
            <ResizeHandle
              side="right"
              onResize={resizeSidecar}
              valueNow={constrainedSidecarWidth}
              valueMin={sidecarResizeMin}
              valueMax={sidecarResizeMax}
            />
          ) : null}
          <div className="flex h-full w-full shrink-0 items-stretch">
            {desktopSidecarVisible ? (
              <AgentTabbedPanel
                projectId={projectId}
                sessionId={state.session?.id}
                events={state.events}
                activeTab={activeSidecarTab}
                onActiveTabChange={setActiveSidecarTab}
                browserInput={browserInput}
                browserSrc={browserSrc}
                onBrowserInputChange={setBrowserInput}
                onBrowserSrcChange={setBrowserSrc}
                onClose={() => closeSidecar("navbar")}
                onAddContext={addContextAttachment}
                hideHeader
              />
            ) : null}
          </div>
        </div>

        {mobileSidecarVisible ? (
          <div
            className="fixed inset-0 z-50 overscroll-contain bg-background/80 p-3 backdrop-blur-sm lg:hidden"
            data-testid="agent-mobile-sidecar-overlay"
            ref={mobileSidecarDialogRef}
            role="dialog"
            aria-modal="true"
            aria-label={t("sidecar.title")}
            tabIndex={-1}
            onKeyDown={onMobileSidecarKeyDown}
          >
            <AgentTabbedPanel
              projectId={projectId}
              sessionId={state.session?.id}
              events={state.events}
              activeTab={activeSidecarTab}
              onActiveTabChange={setActiveSidecarTab}
              browserInput={browserInput}
              browserSrc={browserSrc}
              onBrowserInputChange={setBrowserInput}
              onBrowserSrcChange={setBrowserSrc}
              onClose={() => closeSidecar()}
              onAddContext={addContextAttachment}
              variant="mobile"
              className="flex h-full w-full flex-col rounded-xl border border-border/70 shadow-[0_18px_48px_rgba(36,35,33,0.10)]"
            />
          </div>
        ) : null}
      </div>
    )
  },
)

function createOptimisticTurn({
  text,
  inputParts,
  activeSkillNames,
  sessionId,
  projectId,
  localQueue = false,
  localPendingInterrupt = false,
}: {
  text: string
  inputParts: AgentRuntimeInputPart[]
  activeSkillNames: string[]
  sessionId: string
  projectId?: string | null
  localQueue?: boolean
  localPendingInterrupt?: boolean
}): AgentRuntimeTurn {
  const now = new Date().toISOString()
  return {
    id: `optimistic-${now}`,
    session_id: sessionId,
    project_id: projectId ?? null,
    workspace_id: "pending",
    user_id: "pending",
    input_text: text,
    input_parts: inputParts,
    active_skill_names: activeSkillNames,
    status: "queued",
    model_selection: null,
    model_profile_snapshot: null,
    final_text: null,
    token_usage: null,
    termination_reason: null,
    loop_state: {
      state: "queued",
      optimistic: true,
      ...(localQueue ? { local_queue: true } : {}),
      ...(localPendingInterrupt ? { local_pending_interrupt: true } : {}),
    },
    iteration_count: 0,
    budget_snapshot: null,
    interrupt_requested_at: null,
    error_code: null,
    error_message: null,
    created_at: now,
    updated_at: now,
    started_at: null,
    completed_at: null,
  }
}

function isLocalPendingSubmissionTurn(turn: AgentRuntimeTurn) {
  return (
    turn.loop_state?.local_queue === true ||
    turn.loop_state?.local_pending_interrupt === true
  )
}

function reassignPendingSubmission(
  submission: PendingSubmission,
  sessionId: string,
): PendingSubmission {
  return {
    ...submission,
    sessionId,
    optimisticTurn: { ...submission.optimisticTurn, session_id: sessionId },
  }
}

function StarterSuggestionList({
  suggestions,
  onSelect,
}: {
  suggestions: Array<{
    key: string
    icon: ComponentType<{ className?: string; "aria-hidden"?: boolean }>
    prompt: string
  }>
  onSelect: (prompt: string) => void
}) {
  return (
    <div
      className="absolute inset-x-0 top-full mt-5 w-full overflow-hidden"
      data-testid="agent-starter-suggestions"
    >
      {suggestions.map((suggestion, index) => (
        <button
          key={suggestion.key}
          type="button"
          className={cn(
            "group grid min-h-[32px] w-full grid-cols-[0.875rem_minmax(0,1fr)] items-center gap-2 rounded-[5px] px-4 text-left transition-colors duration-150 hover:bg-foreground/[0.025] focus-visible:relative focus-visible:z-10 focus-visible:bg-foreground/[0.035] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-foreground/18 focus-visible:ring-offset-1 focus-visible:ring-offset-background sm:min-h-[35px]",
            index > 0 && "border-t border-border/75",
          )}
          onClick={() => onSelect(suggestion.prompt)}
        >
          <suggestion.icon
            className="h-3.5 w-3.5 text-muted-foreground/65 transition-colors duration-150 group-hover:text-muted-foreground/85"
            aria-hidden={true}
          />
          <span className="min-w-0 truncate text-[12px] font-normal leading-[18px] tracking-normal text-muted-foreground transition-colors duration-150 group-hover:text-foreground/70 sm:text-[13px]">
            {suggestion.prompt}
          </span>
        </button>
      ))}
    </div>
  )
}

function CommandDiscoveryHints({
  hints,
}: {
  hints: Array<{ key: string; token: string; prefix: string; suffix: string }>
}) {
  const [displayIndex, setDisplayIndex] = useState(0)
  const [swapState, setSwapState] = useState<"" | "is-exit" | "is-enter-start">("")
  const currentHint = hints[displayIndex] ?? hints[0]

  useEffect(() => {
    if (hints.length <= 1) return

    const timers = new Set<ReturnType<typeof setTimeout>>()
    const addTimer = (callback: () => void, delay: number) => {
      const timer = setTimeout(() => {
        timers.delete(timer)
        callback()
      }, delay)
      timers.add(timer)
    }

    const interval = setInterval(() => {
      setSwapState("is-exit")
      addTimer(() => {
        setDisplayIndex((index) => (index + 1) % hints.length)
        setSwapState("is-enter-start")
        addTimer(() => setSwapState(""), 16)
      }, 150)
    }, 5200)

    return () => {
      clearInterval(interval)
      timers.forEach((timer) => clearTimeout(timer))
    }
  }, [hints.length])

  if (!currentHint) return null

  return (
    <div
      className="agent-center-stage pointer-events-none absolute inset-x-14 bottom-24 flex justify-center sm:inset-x-4 sm:bottom-12"
      data-testid="agent-command-discovery-hints"
    >
      <p
        className={cn(
          "t-text-swap inline-flex max-w-[calc(100vw-2rem)] items-center justify-center gap-1.5 truncate text-center text-[12px] font-normal leading-5 tracking-normal text-muted-foreground/75 sm:text-[13px]",
          swapState,
        )}
        aria-label={`${currentHint.prefix} ${currentHint.token} ${currentHint.suffix}`}
      >
        <span className="truncate">{currentHint.prefix}</span>
        <kbd className="rounded-[5px] border border-border/35 bg-foreground/[0.055] px-1.5 py-px font-mono text-[11px] font-normal leading-none text-muted-foreground/85">
          {currentHint.token}
        </kbd>
        <span className="truncate">{currentHint.suffix}</span>
      </p>
    </div>
  )
}

function workflowContextInputFromComposerValue({
  value,
  projectId,
  label,
}: {
  value: string
  projectId?: string | null
  label: string
}): { text: string; workflowParts: AgentRuntimeInputPart[] } {
  let hasWorkflowMention = false
  const text = value
    .replace(WORKFLOW_MENTION_PATTERN, (_match, prefix: string) => {
      hasWorkflowMention = true
      return prefix
    })
    .replace(/\s+([,.!?;:])/g, "$1")
    .replace(/\s+/g, " ")
    .trim()

  if (!hasWorkflowMention) return { text: value.trim(), workflowParts: [] }

  return {
    text: text || label,
    workflowParts: [
      {
        kind: "workflow_ref",
        project_id: projectId || null,
        scope: projectId ? "project" : "global",
      },
    ],
  }
}

function getSessionRemoteConnectionId(metadata: Record<string, unknown> | null | undefined): string {
  const value = metadata?.remote_connection_id
  return typeof value === "string" ? value : ""
}

function maxSidecarWidthForWorkbench(width: number) {
  if (!Number.isFinite(width) || width <= 0) return SIDECAR_MAX_WIDTH
  return Math.min(
    SIDECAR_MAX_WIDTH,
    Math.max(0, Math.floor(width - SIDECAR_MAIN_MIN_WIDTH)),
  )
}

function clampSidecarWidth(width: number, maxWidth = SIDECAR_MAX_WIDTH) {
  const effectiveMax = Math.min(Math.max(maxWidth, 0), SIDECAR_MAX_WIDTH)
  if (effectiveMax <= 0) return 0
  const effectiveMin = Math.min(SIDECAR_MIN_WIDTH, effectiveMax)
  return Math.min(Math.max(width, effectiveMin), effectiveMax)
}
