import type {
  ActiveRunView,
  HistoryEntry,
  RunView,
  SessionSnapshot,
} from "@/lib/agent/contracts"

const now = "2026-08-16T08:00:00.000Z"

export function runFixture(
  overrides: Partial<RunView> = {},
): RunView {
  return {
    id: "run-1",
    session_id: "session-1",
    status: "running",
    phase: "model",
    revision: 1,
    started_at: now,
    completed_at: null,
    termination_reason: null,
    error: null,
    execution_config: {
      settings_revision: 1,
      model: {
        provider: "openai",
        model: "gpt-5.6",
        display_name: "GPT-5.6",
        supports_vision: true,
        supports_reasoning: true,
        supports_tools: true,
      },
      permission_mode: "ask_dangerous",
      workspace_access: "read_write",
      environment_scope: { mode: "auto", environment_ids: [] },
      environment_targets: [
        {
          environment_id: "local",
          display_name: "Local",
          kind: "local",
          host: null,
        },
      ],
    },
    created_at: now,
    updated_at: now,
    ...overrides,
  }
}

export function entryFixture(
  entry: Pick<HistoryEntry, "id" | "type" | "payload"> &
    Partial<HistoryEntry>,
): HistoryEntry {
  return {
    session_id: "session-1",
    run_id: "run-1",
    sequence: 1,
    schema_version: 1,
    created_at: now,
    ...entry,
  } as HistoryEntry
}

function activeRunFixture(
  overrides: Partial<ActiveRunView> = {},
): ActiveRunView {
  return {
    run: runFixture(),
    assistant_draft: null,
    tool_progress: [],
    pending_interaction: null,
    ...overrides,
  }
}

export const emptySnapshotFixture: SessionSnapshot = {
  session: {
    id: "session-1",
    user_id: "user-1",
    workspace_id: "workspace-1",
    project_id: "project-1",
    title: null,
    model: {
      provider: "openai",
      model: "gpt-5.6",
      display_name: "GPT-5.6",
      supports_vision: true,
      supports_reasoning: true,
      supports_tools: true,
    },
    permission_mode: "ask_dangerous",
    workspace_access: "read_write",
    status: "active",
    created_at: now,
    updated_at: now,
  },
  runs: [],
  entries: [],
  active_run: null,
}

export const completedSnapshotFixture: SessionSnapshot = {
  ...emptySnapshotFixture,
  runs: [
    runFixture({
      status: "completed",
      phase: null,
      completed_at: "2026-08-16T08:00:03.000Z",
      termination_reason: "completed",
      revision: 3,
    }),
  ],
  entries: [
    entryFixture({
      id: "entry-user",
      sequence: 1,
      type: "message",
      payload: {
        role: "user",
        parts: [{ id: "user-text", type: "text", text: "Inspect the run" }],
      },
    }),
    entryFixture({
      id: "entry-assistant",
      sequence: 2,
      type: "message",
      payload: {
        role: "assistant",
        parts: [
          {
            id: "reasoning-1",
            type: "reasoning_summary",
            text: "I should inspect the logs first.",
          },
          {
            id: "tool-call-1",
            type: "tool_call",
            call_id: "call-1",
            group_id: "group-1",
            execution_mode: "serial",
            name: "read",
            display_name: "Read logs",
            category: "read",
            summary: "Read the latest run log",
            arguments: { path: "run.log" },
          },
          {
            id: "tool-result-1",
            type: "tool_result",
            call_id: "call-1",
            status: "completed",
            summary: "Read run.log",
            output: { type: "text", text: "Task completed" },
            started_at: "2026-08-16T08:00:01.000Z",
            completed_at: "2026-08-16T08:00:02.000Z",
            error: null,
          },
          {
            id: "assistant-text",
            type: "text",
            text: "The run completed successfully.",
          },
          {
            id: "artifact-1",
            type: "artifact_ref",
            artifact_id: "report-1",
            title: "Run report",
            media_type: "text/markdown",
          },
        ],
      },
    }),
  ],
  active_run: null,
}

export const activeSnapshotFixture: SessionSnapshot = {
  ...emptySnapshotFixture,
  runs: [runFixture()],
  active_run: activeRunFixture({
    assistant_draft: {
      id: "draft-1",
      run_id: "run-1",
      parts: [
        {
          id: "draft-reasoning",
          type: "reasoning_summary",
          text: "Inspecting the workspace",
          end_offset: 24,
        },
        {
          id: "draft-text",
          type: "text",
          text: "I found",
          end_offset: 7,
        },
      ],
    },
    tool_progress: [
      {
        call_id: "call-live",
        group_id: "group-live",
        execution_mode: "parallel",
        name: "search",
        display_name: "Search files",
        category: "search",
        summary: "Search the project",
        arguments: { query: "AgentComposer" },
        status: "running",
        revision: 2,
        started_at: "2026-08-16T08:00:01.000Z",
        completed_at: null,
        input_summary: "AgentComposer",
        output_summary: null,
        error: null,
        public_details: [],
      },
    ],
  }),
}

export const interactionSnapshotFixture: SessionSnapshot = {
  ...emptySnapshotFixture,
  runs: [runFixture({ status: "waiting_user", phase: "interaction" })],
  active_run: activeRunFixture({
    run: runFixture({ status: "waiting_user", phase: "interaction" }),
    pending_interaction: {
      interaction_id: "interaction-1",
      run_id: "run-1",
      revision: 1,
      request: {
        type: "approval",
        call_id: "call-dangerous",
        tool_name: "bash",
        summary: "Remove temporary files",
        input_preview: "rm tmp.txt",
        allowed_responses: ["approve", "reject"],
        risk: {
          level: "high",
          effects: ["Deletes a file"],
          reasons: ["Destructive command"],
          affected_resources: ["tmp.txt"],
        },
      },
    },
  }),
}

export const failedSnapshotFixture: SessionSnapshot = {
  ...emptySnapshotFixture,
  runs: [
    runFixture({
      status: "failed",
      phase: null,
      completed_at: "2026-08-16T08:00:02.000Z",
      termination_reason: "provider_error",
      error: { code: "provider_error", message: "Provider unavailable" },
    }),
  ],
}
