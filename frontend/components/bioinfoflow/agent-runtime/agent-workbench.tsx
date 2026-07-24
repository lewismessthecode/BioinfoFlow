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

import { AgentComposer, type AgentComposerInlineToken } from "./agent-composer"
import { ConnectModelDialog } from "./connect-model-dialog"
import { AgentEnvironmentCard } from "./agent-environment-card"
import { AgentTabbedPanel, type AgentTabbedPanelTab } from "./agent-tabbed-panel"
import { AgentTodoDock } from "./agent-todo-dock"
import { AgentTranscript } from "./agent-transcript"
import { ComposerApprovalPopover } from "./composer-approval-popover"
import {
  LOCAL_TARGET_ID,
  type ExecutionTargetSelection,
} from "./connected-node-selector"
import { jumpToDecisionTarget, scheduleDecisionFocusHandoff } from "./decision-focus"
import { getPendingActions, parseWaitingDecision } from "./pending-actions"
import type { AgentDecisionHandler } from "./types"
import { todosFromArtifact } from "./artifact-viewers"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { ResizeHandle } from "@/components/ui/resize-handle"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useOptionalWorkspaceShell } from "@/components/bioinfoflow/workspace-shell-context"
import { useAgentRuntime } from "@/hooks/use-agent-runtime"
import { useFirstRunContext } from "@/hooks/use-first-run"
import { useLlmSettings } from "@/hooks/use-llm-settings"
import { useIsMobile } from "@/hooks/use-media-query"
import {
  buildAgentRuntimeTimeline,
  deriveTodoDisplayItems,
  listAgentRuntimeSessionArtifacts,
  listAgentRuntimeSkills,
  listAgentRuntimeWorkflowMentions,
  type AgentRuntimeArtifact,
  type AgentExecutionScope,
  type AgentRuntimeFileRefPart,
  type AgentRuntimeInputPart,
  type AgentRuntimeEvent,
  type AgentRuntimeSkill,
  type AgentRuntimeWorkflowMention,
  type AgentModelSelection,
  type AgentPendingStrategy,
  type AgentPermissionMode,
  type AgentRuntimeTurn,
  resolveAgentExecutionTarget,
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

const DEMO_STARTER_SUGGESTIONS = [
  { key: "checkAndRun", icon: CircleCheck },
  { key: "explainInputs", icon: MessageCircle },
  { key: "reviewRun", icon: RotateCcw },
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
  inputDisplayParts?: AgentInputDisplayPart[] | null
  activeSkillNames: string[]
  modelSelection: AgentModelSelection | null
  executionScope: AgentExecutionScope
  optimisticTurn: AgentRuntimeTurn
  sessionId: string
}

type WorkflowMentionLoadState = {
  scopeKey: string
  workflows: AgentRuntimeWorkflowMention[]
  loading: boolean
  error: string | null
}

type AgentInputDisplayPart =
  | { type: "text"; text: string }
  | {
      type: "workflow"
      workflow_id?: string | null
      project_id?: string | null
      scope?: "project" | "global"
      name: string
      version?: string | null
    }
  | { type: "skill"; name: string }

type ActiveComposerTokenKey =
  | { kind: "skill"; name: string }
  | { kind: "workflow"; id: string }

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
    const firstRun = useFirstRunContext()
    const textareaRef = useRef<HTMLTextAreaElement>(null)
    const mobileSidecarDialogRef = useRef<HTMLDivElement>(null)
    const mobileSidecarRestoreFocusRef = useRef<HTMLElement | null>(null)
    const desktopSidecarFocusTargetRef = useRef<"navbar" | null>(null)
    const environmentPanelRef = useRef<HTMLDivElement>(null)
    const composerShellRef = useRef<HTMLDivElement>(null)
    const workbenchRootRef = useRef<HTMLDivElement>(null)
    const isMobile = useIsMobile()
    const [input, setInput] = useState("")
    const [connectModelOpen, setConnectModelOpen] = useState(false)
    const [contextAttachments, setContextAttachments] = useState<AgentRuntimeFileRefPart[]>([])
    const [availableSkills, setAvailableSkills] = useState<AgentRuntimeSkill[]>([])
    const [activeSkillNames, setActiveSkillNames] = useState<string[]>([])
    const [activeComposerTokenKeys, setActiveComposerTokenKeys] = useState<
      ActiveComposerTokenKey[]
    >([])
    const [skillsLoading, setSkillsLoading] = useState(true)
    const [skillsError, setSkillsError] = useState<string | null>(null)
    const currentWorkflowMentionScopeKey = workflowMentionScopeKey(projectId)
    const [workflowMentionLoadState, setWorkflowMentionLoadState] =
      useState<WorkflowMentionLoadState>(() => ({
        scopeKey: currentWorkflowMentionScopeKey,
        workflows: [],
        loading: true,
        error: null,
      }))
    const [activeWorkflowMentions, setActiveWorkflowMentions] = useState<AgentRuntimeWorkflowMention[]>([])
    const demoStarterContext =
      firstRun?.ready && firstRun.starter_context?.project_id === projectId
        ? firstRun.starter_context
        : null
    const demoWorkflow = useMemo<AgentRuntimeWorkflowMention | null>(() => {
      const workflow = demoStarterContext?.workflow
      if (!workflow) return null
      return {
        id: workflow.id,
        name: workflow.name,
        version: workflow.version,
        engine: workflow.engine,
        source: workflow.source,
        scope: workflow.scope,
        projectId: workflow.project_id,
        pinned: true,
      }
    }, [demoStarterContext])
    const workflowMentionStateMatchesScope =
      workflowMentionLoadState.scopeKey === currentWorkflowMentionScopeKey
    const availableWorkflowMentions = workflowMentionStateMatchesScope
      ? workflowMentionLoadState.workflows
      : []
    const workflowMentionsLoading = workflowMentionStateMatchesScope
      ? workflowMentionLoadState.loading
      : true
    const workflowMentionsError = workflowMentionStateMatchesScope
      ? workflowMentionLoadState.error
      : null
    const scopedActiveWorkflowMentions = useMemo(
      () =>
        activeWorkflowMentions.filter((workflow) =>
          projectId
            ? workflow.scope === "project" && workflow.projectId === projectId
            : workflow.scope === "global",
        ),
      [activeWorkflowMentions, projectId],
    )
    const activeComposerTokens = useMemo<AgentComposerInlineToken[]>(() => {
      const tokens = activeComposerTokenKeys.flatMap((token) => {
        if (token.kind === "skill") {
          if (!activeSkillNames.includes(token.name)) return []
          return [
            {
              kind: "skill" as const,
              skill:
                availableSkills.find((skill) => skill.name === token.name) ??
                fallbackAgentRuntimeSkill(token.name),
            },
          ]
        }
        const workflow = scopedActiveWorkflowMentions.find(
          (item) => item.id === token.id,
        )
        return workflow ? [{ kind: "workflow" as const, workflow }] : []
      })
      const orderedKeys = new Set(
        tokens.map((token) =>
          token.kind === "skill"
            ? `skill:${token.skill.name}`
            : `workflow:${token.workflow.id}`,
        ),
      )
      const missingWorkflows = scopedActiveWorkflowMentions
        .filter((workflow) => !orderedKeys.has(`workflow:${workflow.id}`))
        .map((workflow) => ({ kind: "workflow" as const, workflow }))
      const missingSkills = activeSkillNames
        .filter((name) => !orderedKeys.has(`skill:${name}`))
        .map((name) => ({
          kind: "skill" as const,
          skill:
            availableSkills.find((skill) => skill.name === name) ??
            fallbackAgentRuntimeSkill(name),
        }))
      return [...tokens, ...missingWorkflows, ...missingSkills]
    }, [
      activeComposerTokenKeys,
      activeSkillNames,
      availableSkills,
      scopedActiveWorkflowMentions,
    ])
    const [executionSelectionOverride, setExecutionSelectionOverride] = useState<{
      sessionId: string
      value: ExecutionTargetSelection
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
    const [pendingPermissionMode, setPendingPermissionMode] =
      useState<AgentPermissionMode | null>(null)
    const [decisionFocusAnnouncement, setDecisionFocusAnnouncement] = useState({
      message: "",
      sequence: 0,
    })
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
    const {
      models,
      selectedModel,
      isLoading: modelsLoading,
      setSelectedModel,
      refresh: refreshLlmSettings,
    } = useLlmSettings()
    const {
      state,
      eventWindowLimited,
      mode,
      setMode,
      permissionMode,
      setPermissionMode,
      permissionUpdate,
      retryPermissionModeUpdate,
      setActiveSessionId,
      send,
      interrupt,
      decideAction,
    } = useAgentRuntime(projectId, {
      activeSessionId,
      onActiveSessionIdChange,
    })
    const decideActionWithFocus = useCallback<AgentDecisionHandler>(
      async (actionId, decision, options) => {
        if (options) {
          await decideAction(actionId, decision, options)
        } else {
          await decideAction(actionId, decision)
        }
        scheduleDecisionFocusHandoff(actionId, (destination) => {
          setDecisionFocusAnnouncement((current) => ({
            message: t(
              destination === "next"
                ? "decision.focusedNext"
                : "decision.focusedComposer",
            ),
            sequence: current.sequence + 1,
          }))
        })
      },
      [decideAction, t],
    )
    const agentMode = mode ?? "execution"
    const sessionId = state.session?.id ?? ""
    const submissionSessionId = activeSessionId || sessionId || "pending-session"
    const sessionExecutionSelection = useMemo(
      () => getSessionExecutionSelection(state.session),
      [state.session],
    )
    const projectRemoteConnectionId = useMemo(() => {
      if (!projectId) return ""
      const project = workspaceShell?.projects.find((item) => item.id === projectId)
      if (project?.storage_mode !== "remote") return ""
      return typeof project.remote_connection_id === "string"
        ? project.remote_connection_id
        : ""
    }, [projectId, workspaceShell?.projects])
    const projectExecutionSelection = useMemo<ExecutionTargetSelection>(
      () =>
        projectRemoteConnectionId
          ? { mode: "manual", targetIds: [projectRemoteConnectionId] }
          : { mode: "auto" },
      [projectRemoteConnectionId],
    )
    const hasExecutionSelectionOverride =
      executionSelectionOverride?.sessionId === sessionId
    const executionSelection = useMemo<ExecutionTargetSelection>(
      () =>
        hasExecutionSelectionOverride
          ? executionSelectionOverride.value
          : sessionExecutionSelection ||
            (state.session ? { mode: "auto" } : projectExecutionSelection),
      [
        executionSelectionOverride,
        hasExecutionSelectionOverride,
        projectExecutionSelection,
        sessionExecutionSelection,
        state.session,
      ],
    )
    const currentExecutionTargetLabel = useMemo(
      () => currentTargetLabelForSelection(state.events, t),
      [state.events, t],
    )

    const pendingApprovalSummary = useMemo(() => {
      let eligible = 0
      let excluded = 0
      for (const event of getPendingActions(state.events)) {
        const decision = parseWaitingDecision(event)
        if (decision.interaction) excluded += 1
        else eligible += 1
      }
      return { eligible, excluded }
    }, [state.events])

    const requestPermissionMode = useCallback(
      (nextMode: AgentPermissionMode) => {
        if (!setPermissionMode || nextMode === permissionMode) return
        if (
          permissionRank(nextMode) > permissionRank(permissionMode) &&
          pendingApprovalSummary.eligible > 0
        ) {
          setPendingPermissionMode(nextMode)
          return
        }
        void setPermissionMode(nextMode, "future_only")
      },
      [pendingApprovalSummary.eligible, permissionMode, setPermissionMode],
    )

    const confirmPermissionMode = useCallback(
      (pendingStrategy: AgentPendingStrategy) => {
        const nextMode = pendingPermissionMode
        setPendingPermissionMode(null)
        if (!nextMode || !setPermissionMode) return
        void setPermissionMode(nextMode, pendingStrategy)
      },
      [pendingPermissionMode, setPermissionMode],
    )

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
    const workflowsLoadFailedLabel = t("workflows.loadFailed")

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
          setActiveWorkflowMentions([])
          setActiveComposerTokenKeys([])
          setExecutionSelectionOverride(null)
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
      let cancelled = false
      const scopeKey = currentWorkflowMentionScopeKey
      void listAgentRuntimeWorkflowMentions(projectId)
        .then((workflows) => {
          if (!cancelled) {
            setWorkflowMentionLoadState({
              scopeKey,
              workflows,
              loading: false,
              error: null,
            })
          }
        })
        .catch((error) => {
          if (!cancelled) {
            setWorkflowMentionLoadState({
              scopeKey,
              workflows: [],
              loading: false,
              error: error instanceof Error ? error.message : workflowsLoadFailedLabel,
            })
          }
        })
      return () => {
        cancelled = true
      }
    }, [currentWorkflowMentionScopeKey, projectId, workflowsLoadFailedLabel])

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
      setActiveComposerTokenKeys((current) =>
        current.some((token) => token.kind === "skill" && token.name === name)
          ? current
          : [...current, { kind: "skill", name }],
      )
    }, [])

    const removeActiveSkill = useCallback((name: string) => {
      setActiveSkillNames((current) => current.filter((item) => item !== name))
      setActiveComposerTokenKeys((current) =>
        current.filter((token) => token.kind !== "skill" || token.name !== name),
      )
    }, [])

    const addWorkflowMention = useCallback((workflow: AgentRuntimeWorkflowMention) => {
      setActiveWorkflowMentions((current) =>
        current.some((item) => item.id === workflow.id) ? current : [...current, workflow],
      )
      setActiveComposerTokenKeys((current) =>
        current.some((token) => token.kind === "workflow" && token.id === workflow.id)
          ? current
          : [...current, { kind: "workflow", id: workflow.id }],
      )
    }, [])

    const removeWorkflowMention = useCallback((workflowId: string) => {
      setActiveWorkflowMentions((current) =>
        current.filter((item) => item.id !== workflowId),
      )
      setActiveComposerTokenKeys((current) =>
        current.filter(
          (token) => token.kind !== "workflow" || token.id !== workflowId,
        ),
      )
    }, [])

    const fillStarterSuggestion = useCallback((prompt: string) => {
      setInput(prompt)
      window.requestAnimationFrame(() => {
        textareaRef.current?.focus()
        textareaRef.current?.setSelectionRange(prompt.length, prompt.length)
      })
    }, [])

    const handleExecutionSelectionChange = useCallback(
      (selection: ExecutionTargetSelection) => {
        setExecutionSelectionOverride({ sessionId, value: selection })
      },
      [sessionId],
    )

    const sendTurn = useCallback(
      (
        text: string,
        inputParts: AgentRuntimeInputPart[],
        activeSkillNamesSnapshot: string[],
        inputDisplayParts?: AgentInputDisplayPart[] | null,
        modelSelection = selectedModel,
        executionScope: AgentExecutionScope = executionScopeForSelection(
          executionSelection,
        ),
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
            inputDisplayParts,
            activeSkillNames: activeSkillNamesSnapshot,
            sessionId: submissionSessionId,
            projectId,
          })
        const metadata = inputDisplayMetadataFromInputParts(
          inputParts,
          activeSkillNamesSnapshot,
          inputDisplayParts,
        )
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
          executionScope,
          metadata,
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
        executionSelection,
        projectId,
        selectedModel,
        send,
        submissionSessionId,
      ],
    )

    const submitTurn = useCallback(
      (
        text: string,
        inputParts: AgentRuntimeInputPart[],
        activeSkillNamesSnapshot: string[],
        inputDisplayParts?: AgentInputDisplayPart[] | null,
        modelSelection = selectedModel,
      ) => {
        const trimmedText = text.trim()
        if (!trimmedText) return
        const executionScope = executionScopeForSelection(executionSelection)
        if (!hasActiveTurn) {
          sendTurn(
            trimmedText,
            inputParts,
            activeSkillNamesSnapshot,
            inputDisplayParts,
            modelSelection,
            executionScope,
          )
          return
        }

        if (turnPolicy === "queue") {
          const nextOptimisticTurn = createOptimisticTurn({
            text: trimmedText,
            inputParts,
            inputDisplayParts,
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
              inputDisplayParts,
              activeSkillNames: activeSkillNamesSnapshot,
              modelSelection,
              executionScope,
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
            inputDisplayParts,
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
            inputDisplayParts,
            activeSkillNames: activeSkillNamesSnapshot,
            modelSelection,
            executionScope,
            optimisticTurn: nextOptimisticTurn,
            sessionId: submissionSessionId,
          })
          return
        }

        void (async () => {
          await interrupt()
          sendTurn(
            trimmedText,
            inputParts,
            activeSkillNamesSnapshot,
            inputDisplayParts,
            modelSelection,
            executionScope,
          )
        })()
      },
      [
        executionSelection,
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

    const submitDemoStarter = useCallback(
      (prompt: string) => {
        if (!demoWorkflow) return
        if (!selectedModel) {
          setConnectModelOpen(true)
          return
        }
        const inputParts: AgentRuntimeInputPart[] = [
          { type: "text", text: prompt },
          workflowMentionInputPart(demoWorkflow),
        ]
        const inputDisplayParts: AgentInputDisplayPart[] = [
          {
            type: "workflow",
            workflow_id: demoWorkflow.id,
            project_id: demoWorkflow.projectId ?? null,
            scope: demoWorkflow.scope,
            name: demoWorkflow.name,
            version: demoWorkflow.version,
          },
          { type: "text", text: prompt },
        ]
        submitTurn(prompt, inputParts, [], inputDisplayParts, selectedModel)
      },
      [demoWorkflow, selectedModel, submitTurn],
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
        sendTurn(
          next.text,
          next.inputParts,
          next.activeSkillNames,
          next.inputDisplayParts,
          next.modelSelection,
          next.executionScope,
          next.optimisticTurn,
        )
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
          sendTurn(
            next.text,
            next.inputParts,
            next.activeSkillNames,
            next.inputDisplayParts,
            next.modelSelection,
            next.executionScope,
            next.optimisticTurn,
          )
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
      if (!input.trim()) return
      if (!selectedModel) {
        setConnectModelOpen(true)
        return
      }
      const workflowInput = workflowContextInputFromComposerValue({
        value: input,
        projectId,
        label: t("workflowContext.label"),
      })
      const text = workflowInput.text
      if (!text) return
      const inputParts: AgentRuntimeInputPart[] = [
        { type: "text", text },
        ...scopedActiveWorkflowMentions.map(workflowMentionInputPart),
        ...workflowInput.workflowParts,
        ...contextAttachments,
      ]
      const activeSkillNamesSnapshot = [...activeSkillNames]
      const inputDisplayParts = inputDisplayPartsForSubmission({
        text,
        workflowDisplayParts: workflowInput.displayParts,
        activeWorkflowMentions: scopedActiveWorkflowMentions,
        activeSkillNames: activeSkillNamesSnapshot,
        activeComposerTokens,
      })
      submitTurn(
        text,
        inputParts,
        activeSkillNamesSnapshot,
        inputDisplayParts,
        selectedModel,
      )
      setInput("")
      setContextAttachments([])
      setActiveSkillNames([])
      setActiveWorkflowMentions([])
      setActiveComposerTokenKeys([])
    }

    const retryTurn = useCallback(
      (turn: AgentRuntimeTurn) => {
        const text = turn.input_text.trim()
        if (!text) return
        const inputParts =
          turn.input_parts && turn.input_parts.length
            ? retryInputPartsForTurn(turn)
            : [{ type: "text" as const, text }]
        submitTurn(
          text,
          inputParts,
          turn.active_skill_names ?? [],
          inputDisplayPartsFromTurn(turn),
          turn.model_selection ?? null,
        )
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

    const jumpFromMobileSidecar = useCallback(
      (targetId: string) => {
        closeSidecar()
        window.requestAnimationFrame(() => jumpToDecisionTarget(targetId))
      },
      [closeSidecar],
    )

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
    const composerPlaceholders = useMemo(
      () => [
        t("composerPlaceholders.checkWorkflow"),
        t("composerPlaceholders.chooseInputs"),
        t("composerPlaceholders.reviewFailure"),
        t("composerPlaceholders.prepareRun"),
      ],
      [t],
    )
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
        onPermissionModeChange={requestPermissionMode}
        permissionUpdate={permissionUpdate}
        onRetryPermissionModeChange={() => void retryPermissionModeUpdate()}
        models={models}
        selectedModel={selectedModel}
        modelsLoading={modelsLoading}
        onSelectModel={(model) => void setSelectedModel(model)}
        contextAttachments={contextAttachments}
        onRemoveContextAttachment={removeContextAttachment}
        availableSkills={availableSkills}
        activeSkillNames={activeSkillNames}
        activeComposerTokens={activeComposerTokens}
        skillsLoading={skillsLoading}
        skillsError={skillsError}
        onAddActiveSkill={addActiveSkill}
        onRemoveActiveSkill={removeActiveSkill}
        availableWorkflowMentions={availableWorkflowMentions}
        activeWorkflowMentions={scopedActiveWorkflowMentions}
        workflowMentionsLoading={workflowMentionsLoading}
        workflowMentionsError={workflowMentionsError}
        onAddWorkflowMention={addWorkflowMention}
        onRemoveWorkflowMention={removeWorkflowMention}
        tokenUsageSummary={state.session?.token_usage_summary}
        executionSelection={executionSelection}
        currentExecutionTargetLabel={
          hasActiveTurn ? currentExecutionTargetLabel : null
        }
        onExecutionSelectionChange={handleExecutionSelectionChange}
        compactControls={desktopSidecarVisible}
        presentation={composerDocked ? "dock" : "center"}
        contextTitle={null}
        ariaLabel={t("composerPlaceholder")}
        placeholderSuggestions={composerPlaceholders}
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
        <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
          <span key={decisionFocusAnnouncement.sequence}>
            {decisionFocusAnnouncement.message}
          </span>
        </div>
        <Dialog
          open={pendingPermissionMode !== null}
          onOpenChange={(open) => {
            if (!open) setPendingPermissionMode(null)
          }}
        >
          <DialogContent showCloseButton={false}>
            <DialogHeader>
              <DialogTitle>{t("permission.confirm.title")}</DialogTitle>
              <DialogDescription>
                {t("permission.confirm.description", {
                  eligible: pendingApprovalSummary.eligible,
                  excluded: pendingApprovalSummary.excluded,
                })}
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-2">
              <Button
                type="button"
                variant="secondary"
                className="h-auto justify-start rounded-lg px-3 py-2.5 text-left"
                onClick={() => confirmPermissionMode("future_only")}
                aria-label={t("permission.confirm.futureOnly")}
              >
                <span className="grid gap-0.5">
                  <span>{t("permission.confirm.futureOnly")}</span>
                  <span className="text-xs font-normal text-muted-foreground">
                    {t("permission.confirm.futureOnlyDescription")}
                  </span>
                </span>
              </Button>
              <Button
                type="button"
                variant="outline"
                className="h-auto justify-start rounded-lg px-3 py-2.5 text-left"
                onClick={() => confirmPermissionMode("approve_pending_tools")}
                aria-label={t("permission.confirm.approvePending", {
                  count: pendingApprovalSummary.eligible,
                })}
              >
                <span className="grid gap-0.5">
                  <span>
                    {t("permission.confirm.approvePending", {
                      count: pendingApprovalSummary.eligible,
                    })}
                  </span>
                  <span className="text-xs font-normal text-muted-foreground">
                    {t("permission.confirm.approvePendingDescription")}
                  </span>
                </span>
              </Button>
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setPendingPermissionMode(null)}
              >
                {t("permission.confirm.cancel")}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
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
                onDecision={decideActionWithFocus}
                onRetryTurn={retryTurn}
                responseActionsBusy={hasActiveTurn}
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
                {!modelsLoading && !selectedModel ? (
                  <div className="mb-3 flex justify-center">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-8 rounded-[6px] border-border/80 bg-background px-3 text-xs shadow-none"
                      onClick={() => setConnectModelOpen(true)}
                    >
                      {t("connectModel.action")}
                    </Button>
                  </div>
                ) : null}
                {!composerDocked ? (
                  <div data-testid="agent-composer-shell" data-placement="center">
                    {composer}
                  </div>
                ) : null}
                {!composerDocked && !input.trim() ? (
                  <StarterSuggestionList
                    suggestions={(demoStarterContext
                      ? DEMO_STARTER_SUGGESTIONS
                      : STARTER_SUGGESTIONS
                    )
                      .slice(
                        0,
                        desktopSidecarVisible
                          ? 3
                          : demoStarterContext
                            ? DEMO_STARTER_SUGGESTIONS.length
                            : STARTER_SUGGESTIONS.length,
                      )
                      .map((suggestion) => ({
                        key: suggestion.key,
                        icon: suggestion.icon,
                        prompt: t(
                          demoStarterContext
                            ? `demoStarterSuggestions.${suggestion.key}.prompt`
                            : `starterSuggestions.${suggestion.key}.prompt`,
                        ),
                      }))}
                    onSelect={(key, prompt) => {
                      if (demoStarterContext && key === "checkAndRun") {
                        submitDemoStarter(prompt)
                        return
                      }
                      fillStarterSuggestion(prompt)
                    }}
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
          {connectModelOpen ? (
            <ConnectModelDialog
              open
              onOpenChange={setConnectModelOpen}
              setSelectedModel={setSelectedModel}
              refreshSettings={refreshLlmSettings}
              onConnected={() => {
                setTimeout(() => textareaRef.current?.focus(), 0)
              }}
            />
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
              onJumpToPendingDecision={jumpFromMobileSidecar}
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
  inputDisplayParts,
  activeSkillNames,
  sessionId,
  projectId,
  localQueue = false,
  localPendingInterrupt = false,
}: {
  text: string
  inputParts: AgentRuntimeInputPart[]
  inputDisplayParts?: AgentInputDisplayPart[] | null
  activeSkillNames: string[]
  sessionId: string
  projectId?: string | null
  localQueue?: boolean
  localPendingInterrupt?: boolean
}): AgentRuntimeTurn {
  const now = new Date().toISOString()
  const metadata = inputDisplayMetadataFromInputParts(
    inputParts,
    activeSkillNames,
    inputDisplayParts,
  )
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
    model_profile_snapshot: metadata ? { metadata } : null,
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

function permissionRank(mode: AgentPermissionMode) {
  if (mode === "ask_each_action") return 0
  if (mode === "guarded_auto") return 1
  return 2
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
  onSelect: (key: string, prompt: string) => void
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
          onClick={() => onSelect(suggestion.key, suggestion.prompt)}
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
}): {
  text: string
  workflowParts: AgentRuntimeInputPart[]
  displayParts: AgentInputDisplayPart[] | null
} {
  let hasWorkflowMention = false
  const displayParts: AgentInputDisplayPart[] = []
  let displayCursor = 0
  const text = value
    .replace(WORKFLOW_MENTION_PATTERN, (_match, prefix: string, offset: number) => {
      hasWorkflowMention = true
      const tokenStart = offset + prefix.length
      if (tokenStart > displayCursor) {
        displayParts.push({ type: "text", text: value.slice(displayCursor, tokenStart) })
      }
      displayParts.push({
        type: "workflow",
        project_id: projectId || null,
        scope: projectId ? "project" : "global",
        name: "workflow",
        version: null,
      })
      displayCursor = tokenStart + "@workflow".length
      return prefix
    })
    .replace(/\s+([,.!?;:])/g, "$1")
    .replace(/\s+/g, " ")
    .trim()

  if (!hasWorkflowMention) {
    return { text: value.trim(), workflowParts: [], displayParts: null }
  }

  if (displayCursor < value.length) {
    displayParts.push({ type: "text", text: value.slice(displayCursor) })
  }

  return {
    text: text || label,
    displayParts: trimInputDisplayTextParts(displayParts),
    workflowParts: [
      {
        kind: "workflow_ref",
        project_id: projectId || null,
        scope: projectId ? "project" : "global",
      },
    ],
  }
}

function inputDisplayPartsForSubmission({
  text,
  workflowDisplayParts,
  activeWorkflowMentions,
  activeSkillNames,
  activeComposerTokens,
}: {
  text: string
  workflowDisplayParts?: AgentInputDisplayPart[] | null
  activeWorkflowMentions: AgentRuntimeWorkflowMention[]
  activeSkillNames: string[]
  activeComposerTokens?: AgentComposerInlineToken[]
}): AgentInputDisplayPart[] | null {
  const orderedTokenParts = (activeComposerTokens?.length
    ? activeComposerTokens
    : [
        ...activeWorkflowMentions.map((workflow) => ({
          kind: "workflow" as const,
          workflow,
        })),
        ...activeSkillNames.map((name) => ({
          kind: "skill" as const,
          skill: fallbackAgentRuntimeSkill(name),
        })),
      ]
  ).map((token): AgentInputDisplayPart => {
    if (token.kind === "skill") return { type: "skill", name: token.skill.name }
    return {
      type: "workflow",
      workflow_id: token.workflow.id,
      project_id: token.workflow.projectId ?? null,
      scope: token.workflow.scope,
      name: token.workflow.name,
      version: token.workflow.version,
    }
  })
  const parts: AgentInputDisplayPart[] = [
    ...orderedTokenParts,
    ...(workflowDisplayParts?.length ? workflowDisplayParts : [{ type: "text" as const, text }]),
  ]
  const trimmedParts = trimInputDisplayTextParts(parts)
  return trimmedParts.some((part) => part.type !== "text") ? trimmedParts : null
}

function trimInputDisplayTextParts(parts: AgentInputDisplayPart[]) {
  const nextParts = parts
    .map((part) => {
      if (part.type !== "text") return part
      return { ...part, text: part.text.replace(/\s+/g, " ") }
    })
    .filter((part) => part.type !== "text" || part.text.length > 0)
  const firstText = nextParts[0]
  if (firstText?.type === "text") {
    firstText.text = firstText.text.trimStart()
  }
  const lastText = nextParts.at(-1)
  if (lastText?.type === "text") {
    lastText.text = lastText.text.trimEnd()
  }
  return nextParts.filter((part) => part.type !== "text" || part.text.length > 0)
}

function workflowMentionInputPart(
  workflow: AgentRuntimeWorkflowMention,
): AgentRuntimeInputPart {
  return {
    kind: "workflow_ref",
    workflow_id: workflow.id,
    project_id: workflow.projectId ?? null,
    scope: workflow.scope,
    display_name: workflow.name,
    display_version: workflow.version,
  }
}

function inputDisplayMetadataFromInputParts(
  inputParts: AgentRuntimeInputPart[],
  activeSkillNames: string[] = [],
  inputDisplayParts?: AgentInputDisplayPart[] | null,
): Record<string, unknown> | null {
  const workflowMentions = inputParts
    .map((part) => {
      if (!("kind" in part) || part.kind !== "workflow_ref") return null
      const name = part.display_name?.trim()
      if (!name) return null
      return {
        workflow_id: part.workflow_id ?? null,
        project_id: part.project_id ?? null,
        scope: part.scope,
        name,
        version: part.display_version?.trim() || null,
      }
    })
    .filter((item): item is NonNullable<typeof item> => Boolean(item))

  const inlineParts = normalizeInputDisplayParts(inputDisplayParts)
  const inputDisplay: Record<string, unknown> = {}
  if (workflowMentions.length) inputDisplay.workflow_mentions = workflowMentions
  if (inlineParts.length) inputDisplay.inline_parts = inlineParts
  if (!Object.keys(inputDisplay).length && activeSkillNames.length) {
    inputDisplay.inline_parts = normalizeInputDisplayParts(
      inputDisplayPartsForSubmission({
        text: "",
        workflowDisplayParts: null,
        activeWorkflowMentions: [],
        activeSkillNames,
      }),
    )
  }
  return Object.keys(inputDisplay).length ? { input_display: inputDisplay } : null
}

function normalizeInputDisplayParts(inputDisplayParts?: AgentInputDisplayPart[] | null) {
  if (!inputDisplayParts?.length) return []
  return inputDisplayParts.flatMap((part) => {
    if (part.type === "text") {
      return part.text ? [{ type: "text", text: part.text }] : []
    }
    if (part.type === "skill") {
      const name = part.name.trim()
      return name ? [{ type: "skill", name }] : []
    }
    const name = part.name.trim()
    if (!name) return []
    return [
      {
        type: "workflow",
        workflow_id: part.workflow_id ?? null,
        project_id: part.project_id ?? null,
        scope: part.scope,
        name,
        version: part.version?.trim() || null,
      },
    ]
  })
}

type WorkflowInputDisplayMetadata = {
  workflow_id?: string | null
  project_id?: string | null
  scope?: "project" | "global"
  name: string
  version?: string | null
}

function retryInputPartsForTurn(turn: AgentRuntimeTurn): AgentRuntimeInputPart[] {
  const inputParts = turn.input_parts ?? []
  const workflowDisplays = workflowInputDisplayMetadataFromTurn(turn)
  if (!workflowDisplays.length) return inputParts

  return inputParts.map((part) => {
    if (!("kind" in part) || part.kind !== "workflow_ref" || part.display_name) {
      return part
    }
    const display = workflowDisplays.find((item) =>
      workflowDisplayMatchesInputPart(item, part),
    )
    if (!display) return part
    return {
      ...part,
      display_name: display.name,
      display_version: display.version ?? null,
    }
  })
}

function workflowInputDisplayMetadataFromTurn(
  turn: AgentRuntimeTurn,
): WorkflowInputDisplayMetadata[] {
  const metadata = turn.model_profile_snapshot?.metadata
  if (!isRecord(metadata)) return []
  const inputDisplay = metadata.input_display
  if (!isRecord(inputDisplay)) return []
  const workflowMentions = inputDisplay.workflow_mentions
  if (!Array.isArray(workflowMentions)) return []

  return workflowMentions.flatMap((item) => {
    if (!isRecord(item) || typeof item.name !== "string" || !item.name.trim()) {
      return []
    }
    return [
      {
        workflow_id: nullableString(item.workflow_id),
        project_id: nullableString(item.project_id),
        scope: item.scope === "project" || item.scope === "global" ? item.scope : undefined,
        name: item.name.trim(),
        version: nullableString(item.version),
      },
    ]
  })
}

function inputDisplayPartsFromTurn(turn: AgentRuntimeTurn): AgentInputDisplayPart[] | null {
  const metadata = turn.model_profile_snapshot?.metadata
  if (!isRecord(metadata)) return null
  const inputDisplay = metadata.input_display
  if (!isRecord(inputDisplay)) return null
  const inlineParts = inputDisplay.inline_parts
  if (!Array.isArray(inlineParts)) return null
  const parts = inlineParts.flatMap((item) => inputDisplayPartFromMetadata(item))
  return parts.length ? parts : null
}

function inputDisplayPartFromMetadata(item: unknown): AgentInputDisplayPart[] {
  if (!isRecord(item) || typeof item.type !== "string") return []
  if (item.type === "text") {
    return typeof item.text === "string" && item.text
      ? [{ type: "text", text: item.text }]
      : []
  }
  if (item.type === "skill") {
    return typeof item.name === "string" && item.name.trim()
      ? [{ type: "skill", name: item.name.trim() }]
      : []
  }
  if (item.type !== "workflow" || typeof item.name !== "string" || !item.name.trim()) {
    return []
  }
  return [
    {
      type: "workflow",
      workflow_id: nullableString(item.workflow_id),
      project_id: nullableString(item.project_id),
      scope: item.scope === "project" || item.scope === "global" ? item.scope : undefined,
      name: item.name.trim(),
      version: nullableString(item.version),
    },
  ]
}

function workflowDisplayMatchesInputPart(
  display: WorkflowInputDisplayMetadata,
  part: Extract<AgentRuntimeInputPart, { kind: "workflow_ref" }>,
) {
  if (part.workflow_id && display.workflow_id === part.workflow_id) return true
  if (part.workflow_id) return false
  if (display.workflow_id) return false
  const partProjectId = part.project_id ?? null
  const displayProjectId = display.project_id ?? null
  const scopeMatches = part.scope ? display.scope === part.scope : true
  return displayProjectId === partProjectId && scopeMatches
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function nullableString(value: unknown): string | null {
  return typeof value === "string" ? value : null
}

function workflowMentionScopeKey(projectId?: string | null) {
  return projectId ? `project:${projectId}` : "global"
}

function getSessionRemoteConnectionId(
  session: Parameters<typeof resolveAgentExecutionTarget>[0],
): string {
  const target = resolveAgentExecutionTarget(session)
  return target.kind === "remote_ssh" ? target.remoteConnectionId : ""
}

function getSessionExecutionSelection(
  session: Parameters<typeof resolveAgentExecutionTarget>[0],
): ExecutionTargetSelection | null {
  const scope = session?.execution_scope ?? executionScopeFromMetadata(session?.metadata)
  if (scope?.mode === "auto") return { mode: "auto" }
  if (scope?.mode === "manual") {
    const targetIds = (scope.selected_targets ?? [])
      .map((target) => {
        const kind = target.kind ?? target.type
        if (kind === "local") return LOCAL_TARGET_ID
        if (kind === "remote_ssh") {
          return target.remote_connection_id ?? target.connection_id ?? ""
        }
        return ""
      })
      .filter(Boolean)
    return { mode: "manual", targetIds: targetIds.length ? targetIds : [LOCAL_TARGET_ID] }
  }

  const remoteConnectionId = getSessionRemoteConnectionId(session)
  if (remoteConnectionId) {
    return { mode: "manual", targetIds: [remoteConnectionId] }
  }
  return null
}

function executionScopeForSelection(
  selection: ExecutionTargetSelection,
): AgentExecutionScope {
  if (selection.mode === "auto") return { mode: "auto" }
  return {
    mode: "manual",
    selected_targets: selection.targetIds.map((targetId) =>
      targetId === LOCAL_TARGET_ID
        ? { kind: "local", type: "local" }
        : {
            kind: "remote_ssh",
            type: "remote_ssh",
            connection_id: targetId,
            remote_connection_id: targetId,
          },
    ),
  }
}

function executionScopeFromMetadata(metadata?: Record<string, unknown> | null) {
  const scope = metadata?.execution_scope
  if (!scope || typeof scope !== "object") return null
  return scope as AgentExecutionScope
}

function currentTargetLabelForSelection(
  events: AgentRuntimeEvent[],
  t: ReturnType<typeof useTranslations>,
) {
  const sortedEvents = [...events].sort(
    (left, right) =>
      right.seq - left.seq ||
      right.created_at.localeCompare(left.created_at) ||
      right.id.localeCompare(left.id),
  )
  for (const event of sortedEvents) {
    if (event.type !== "action.risk_assessed") continue
    const label = runtimeTargetLabel(event.payload.target, t)
    if (label) return label
  }
  return null
}

function runtimeTargetLabel(
  target: unknown,
  t: ReturnType<typeof useTranslations>,
) {
  if (!target || typeof target !== "object" || Array.isArray(target)) return null
  const record = target as Record<string, unknown>
  const kind = stringValue(record.kind) ?? stringValue(record.type)
  if (kind === "local") return t("runtimeLocation.local.label")
  if (kind !== "remote_ssh") return null

  const authority = [
    stringValue(record.identity),
    stringValue(record.trust_domain) ?? stringValue(record.trustDomain),
  ]
    .filter(Boolean)
    .join("@")
  return (
    authority ||
    stringValue(record.connection_id) ||
    stringValue(record.connectionId) ||
    stringValue(record.remote_connection_id) ||
    stringValue(record.remoteConnectionId)
  )
}

function stringValue(value: unknown) {
  return typeof value === "string" && value.trim() ? value.trim() : null
}

function fallbackAgentRuntimeSkill(name: string): AgentRuntimeSkill {
  return {
    name,
    version: "",
    description: name,
    tags: [],
  }
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
