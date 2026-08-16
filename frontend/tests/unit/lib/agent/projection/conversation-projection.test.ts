import { describe, expect, it } from "vitest"

import type { ApprovalRequest } from "@/lib/agent/contracts"
import { createConversationProjection } from "@/lib/agent/projection/conversation-projection"

import {
  activeSnapshotFixture,
  completedSnapshotFixture,
  emptySnapshotFixture,
  entryFixture,
  failedSnapshotFixture,
  interactionSnapshotFixture,
  runFixture,
} from "../fixtures/presentation-contract"

describe("Conversation projection", () => {
  it("projects notice and recovery localization metadata without coupling UI to raw copy", () => {
    const result = createConversationProjection({
      ...interactionSnapshotFixture,
      entries: [
        entryFixture({
          id: "notice-timeout",
          type: "notice",
          payload: {
            code: "run_timeout_exceeded",
            message: "Backend-owned English timeout text",
            params: { limit_seconds: 300 },
            details: null,
          },
        }),
      ],
      active_run: interactionSnapshotFixture.active_run
        ? {
            ...interactionSnapshotFixture.active_run,
            pending_interaction: {
              ...interactionSnapshotFixture.active_run.pending_interaction!,
              request: {
                type: "recovery",
                call_id: "call-recovery",
                tool_name: "bash",
                message: "Backend-owned English recovery text",
                message_code: "unknown_tool_effect",
                message_params: { tool_name: "bash" },
                options: [
                  { id: "inspect", label: "Inspect", description: "", recommended: false },
                  { id: "retry", label: "Retry", description: "", recommended: false },
                  { id: "cancel", label: "Cancel", description: "", recommended: false },
                ],
              },
            },
          }
        : null,
    })
    if (!result.ok) throw new Error(result.diagnostic.message)

    expect(result.view.transcript).toEqual([
      expect.objectContaining({
        type: "notice",
        code: "run_timeout_exceeded",
        params: { limit_seconds: 300 },
        fallback: "Backend-owned English timeout text",
      }),
      expect.objectContaining({
        type: "interaction",
        request: expect.objectContaining({
          type: "recovery",
          messageCode: "unknown_tool_effect",
          messageParams: { tool_name: "bash" },
          messageFallback: "Backend-owned English recovery text",
        }),
      }),
    ])
  })

  it("projects an empty transport snapshot into a stable draft Conversation View", () => {
    const result = createConversationProjection(emptySnapshotFixture)

    expect(result).toMatchObject({
      ok: true,
      view: {
        protocolVersion: 1,
        conversation: {
          id: "session-1",
          title: null,
          status: "active",
          workspaceId: "workspace-1",
          projectId: "project-1",
        },
        composer: {
          placement: "centered",
          canSend: true,
          settings: {
            model: {
              provider: "openai",
              model: "gpt-5.6",
              displayName: "GPT-5.6",
            },
            permissionMode: "ask_dangerous",
            workspaceAccess: "read_write",
            revision: 1,
            environmentScope: { mode: "auto", environmentIds: [] },
          },
          capabilities: {
            modelSelection: true,
            permissionSelection: true,
            environmentSelection: {
              auto: true,
              manualMultiSelect: true,
            },
            planMode: false,
          },
        },
        transcript: [],
        activeWork: null,
      },
    })
  })

  it("projects completed history without a redundant success outcome row", () => {
    const result = createConversationProjection(completedSnapshotFixture)
    if (!result.ok) throw new Error(result.diagnostic.message)

    expect(result.view.composer.placement).toBe("docked")
    expect(result.view.transcript).toEqual([
      expect.objectContaining({
        type: "message",
        id: "entry-user:user-text",
        role: "user",
        text: "Inspect the run",
      }),
      expect.objectContaining({
        type: "reasoning",
        id: "entry-assistant:reasoning-1",
        text: "I should inspect the logs first.",
        streaming: false,
      }),
      expect.objectContaining({
        type: "activity_group",
        id: "entry-assistant:activity:group-1",
        executionMode: "serial",
        activities: [
          expect.objectContaining({
            callId: "call-1",
            status: "completed",
            output: { type: "text", text: "Task completed" },
          }),
        ],
      }),
      expect.objectContaining({
        type: "message",
        id: "entry-assistant:assistant-text",
        role: "assistant",
        text: "The run completed successfully.",
      }),
      expect.objectContaining({
        type: "artifact",
        artifactId: "report-1",
        title: "Run report",
      }),
    ])
    expect(result.view.runs).toEqual([
      expect.objectContaining({ id: "run-1", status: "completed" }),
    ])
  })

  it("keeps only the latest Run revision without surfacing a success outcome", () => {
    const result = createConversationProjection({
      ...completedSnapshotFixture,
      runs: [
        {
          ...completedSnapshotFixture.runs[0],
          revision: 2,
          status: "failed",
          termination_reason: "runtime_failed",
          error: {
            code: "runtime_failed",
            message: "The Agent runtime stopped unexpectedly.",
          },
        },
        {
          ...completedSnapshotFixture.runs[0],
          revision: 3,
          status: "completed",
          termination_reason: "completed",
          error: null,
        },
      ],
    })
    if (!result.ok) throw new Error(result.diagnostic.message)

    const outcomes = result.view.transcript.filter(
      (block) => block.type === "outcome" && block.runId === "run-1",
    )
    expect(outcomes).toEqual([])
    expect(result.view.runs.filter((run) => run.id === "run-1")).toHaveLength(1)
    expect(result.view.runs[0]).toEqual(
      expect.objectContaining({ id: "run-1", status: "completed" }),
    )
  })

  it("inserts failed and cancelled outcomes after the final block for their Run", () => {
    const result = createConversationProjection({
      ...emptySnapshotFixture,
      runs: [
        runFixture({
          id: "run-failed",
          status: "failed",
          phase: null,
          revision: 2,
          completed_at: "2026-08-16T08:00:02.000Z",
          termination_reason: "runtime_failed",
          error: { code: "runtime_failed", message: "Runtime failed" },
        }),
        runFixture({
          id: "run-cancelled",
          status: "cancelled",
          phase: null,
          revision: 2,
          completed_at: "2026-08-16T08:01:02.000Z",
          termination_reason: "user_cancelled",
        }),
        runFixture({
          id: "run-completed",
          status: "completed",
          phase: null,
          revision: 2,
          completed_at: "2026-08-16T08:02:02.000Z",
          termination_reason: "completed",
        }),
      ],
      entries: [
        entryFixture({
          id: "failed-message",
          run_id: "run-failed",
          sequence: 1,
          type: "message",
          payload: {
            role: "assistant",
            parts: [{ id: "failed-text", type: "text", text: "First run" }],
          },
        }),
        entryFixture({
          id: "cancelled-message",
          run_id: "run-cancelled",
          sequence: 2,
          type: "message",
          payload: {
            role: "assistant",
            parts: [{ id: "cancelled-text", type: "text", text: "Second run" }],
          },
        }),
        entryFixture({
          id: "completed-message",
          run_id: "run-completed",
          sequence: 3,
          type: "message",
          payload: {
            role: "assistant",
            parts: [{ id: "completed-text", type: "text", text: "Third run" }],
          },
        }),
      ],
    })
    if (!result.ok) throw new Error(result.diagnostic.message)

    expect(
      result.view.transcript.map((block) =>
        block.type === "outcome"
          ? `${block.runId}:${block.status}`
          : `${block.runId}:${block.type}`,
      ),
    ).toEqual([
      "run-failed:message",
      "run-failed:failed",
      "run-cancelled:message",
      "run-cancelled:cancelled",
      "run-completed:message",
    ])
  })

  it("merges active tool and interaction state into matching durable history", () => {
    const waitingRun = runFixture({
      status: "waiting_user",
      phase: "interaction",
      revision: 4,
    })
    const request: ApprovalRequest = {
      type: "approval",
      call_id: "call-1",
      tool_name: "bash",
      summary: "Run the requested command",
      input_preview: "echo ok",
      allowed_responses: ["approve", "reject"],
      risk: {
        level: "high",
        effects: ["execute"],
        reasons: ["requires approval"],
        affected_resources: [],
      },
    }
    const result = createConversationProjection({
      ...emptySnapshotFixture,
      runs: [waitingRun],
      entries: [
        entryFixture({
          id: "assistant-tools",
          sequence: 1,
          type: "message",
          payload: {
            role: "assistant",
            parts: [
              {
                id: "tool-call",
                type: "tool_call",
                call_id: "call-1",
                group_id: "group-1",
                execution_mode: "serial",
                name: "bash",
                display_name: "Bash",
                category: "command",
                summary: "Bash: Check the workspace",
                arguments: {},
              },
            ],
          },
        }),
        entryFixture({
          id: "approval-request",
          sequence: 2,
          type: "interaction_request",
          payload: { interaction_id: "interaction-1", request },
        }),
      ],
      active_run: {
        run: waitingRun,
        assistant_draft: null,
        tool_progress: [
          {
            call_id: "call-1",
            group_id: "group-1",
            execution_mode: "serial",
            name: "bash",
            display_name: "Bash",
            category: "command",
            summary: "Bash: Check the workspace",
            arguments: {},
            status: "interaction_required",
            revision: 3,
            started_at: "2026-08-16T08:00:00.000Z",
            completed_at: null,
            input_summary: "Check the workspace",
            output_summary: null,
            error: null,
            public_details: [
              {
                id: "command",
                kind: "command",
                label: null,
                value: "echo ok",
                format: "code",
                copyable: true,
                truncated: false,
                redacted: false,
              },
            ],
          },
        ],
        pending_interaction: {
          interaction_id: "interaction-1",
          run_id: "run-1",
          revision: 1,
          request,
        },
      },
    })
    if (!result.ok) throw new Error(result.diagnostic.message)

    const groups = result.view.transcript.filter(
      (block) => block.type === "activity_group",
    )
    expect(groups).toHaveLength(1)
    expect(groups[0]).toMatchObject({
      activities: [
        expect.objectContaining({
          callId: "call-1",
          summary: "Bash: Check the workspace",
          status: "interaction_required",
          details: [expect.objectContaining({ kind: "command", value: "echo ok" })],
        }),
      ],
    })
    expect(
      result.view.transcript.filter((block) => block.type === "interaction"),
    ).toEqual([
      expect.objectContaining({
        interactionId: "interaction-1",
        status: "pending",
      }),
    ])
  })

  it("projects live draft and tool progress through the same Transcript Block model", () => {
    const result = createConversationProjection(activeSnapshotFixture)
    if (!result.ok) throw new Error(result.diagnostic.message)

    expect(result.view.activeWork).toMatchObject({
      runId: "run-1",
      status: "running",
      phase: "model",
    })
    expect(result.view.transcript).toEqual([
      expect.objectContaining({
        type: "reasoning",
        id: "draft:draft-1:draft-reasoning",
        text: "Inspecting the workspace",
        streaming: true,
      }),
      expect.objectContaining({
        type: "message",
        id: "draft:draft-1:draft-text",
        role: "assistant",
        text: "I found",
        streaming: true,
      }),
      expect.objectContaining({
        type: "activity_group",
        id: "active:run-1:activity:group-live",
        activities: [
          expect.objectContaining({
            callId: "call-live",
            status: "running",
          }),
        ],
      }),
    ])
  })

  it("preserves live reasoning trace provenance and timing metadata", () => {
    const activeRun = activeSnapshotFixture.active_run
    expect(activeRun).not.toBeNull()
    if (!activeRun) return

    const snapshot = {
      ...activeSnapshotFixture,
      active_run: {
        ...activeRun,
        assistant_draft: {
          id: "draft-live-reasoning",
          run_id: "run-1",
          parts: [
            {
              id: "trace-live",
              type: "reasoning_trace" as const,
              text: "Inspecting the scheduler state",
              end_offset: 30,
              provider: "deepseek",
              model: "deepseek-reasoner",
              source: "reasoning_content",
              truncated: true,
              started_at: "2026-08-16T08:00:00.000Z",
              completed_at: "2026-08-16T08:00:02.500Z",
            },
          ],
        },
      },
    }

    const result = createConversationProjection(snapshot)
    if (!result.ok) throw new Error(result.diagnostic.message)

    expect(result.view.transcript[0]).toEqual({
      type: "reasoning",
      id: "draft:draft-live-reasoning:trace-live",
      runId: "run-1",
      createdAt: "2026-08-16T08:00:00.000Z",
      text: "Inspecting the scheduler state",
      streaming: true,
      provider: "deepseek",
      model: "deepseek-reasoner",
      sourceField: "reasoning_content",
      truncated: true,
      startedAt: "2026-08-16T08:00:00.000Z",
      completedAt: "2026-08-16T08:00:02.500Z",
      durationMs: 2500,
    })
  })

  it("uses each Run's immutable model snapshot for reasoning and audit projection", () => {
    const snapshot = {
      ...activeSnapshotFixture,
      session: {
        ...activeSnapshotFixture.session,
        model: {
          ...activeSnapshotFixture.session.model,
          provider: "anthropic",
          model: "claude-next",
          display_name: "Claude Next",
        },
      },
      runs: activeSnapshotFixture.runs.map((run) => ({
        ...run,
        execution_config: {
          ...run.execution_config!,
          settings_revision: 4,
          model: {
            ...run.execution_config!.model,
            provider: "openai",
            model: "gpt-run-snapshot",
            display_name: "GPT Run Snapshot",
          },
        },
      })),
      active_run: activeSnapshotFixture.active_run
        ? {
            ...activeSnapshotFixture.active_run,
            run: {
              ...activeSnapshotFixture.active_run.run,
              execution_config: {
                ...activeSnapshotFixture.active_run.run.execution_config!,
                settings_revision: 4,
                model: {
                  ...activeSnapshotFixture.active_run.run.execution_config!.model,
                  provider: "openai",
                  model: "gpt-run-snapshot",
                  display_name: "GPT Run Snapshot",
                },
              },
            },
          }
        : null,
    }

    const result = createConversationProjection(snapshot)
    if (!result.ok) throw new Error(result.diagnostic.message)

    expect(result.view.runs).toEqual([
      expect.objectContaining({
        id: "run-1",
        executionConfig: expect.objectContaining({
          settingsRevision: 4,
          model: expect.objectContaining({ model: "gpt-run-snapshot" }),
        }),
      }),
    ])
    expect(result.view.transcript[0]).toMatchObject({
      type: "reasoning",
      provider: "openai",
      model: "gpt-run-snapshot",
    })

    const completedResult = createConversationProjection({
      ...completedSnapshotFixture,
      session: snapshot.session,
      runs: completedSnapshotFixture.runs.map((run) => ({
        ...run,
        execution_config: snapshot.runs[0].execution_config,
      })),
    })
    if (!completedResult.ok) {
      throw new Error(completedResult.diagnostic.message)
    }
    expect(completedResult.view.transcript[1]).toMatchObject({
      type: "reasoning",
      streaming: false,
      provider: "openai",
      model: "gpt-run-snapshot",
    })
  })

  it("projects a pending approval as a durable interaction block", () => {
    const result = createConversationProjection(interactionSnapshotFixture)
    if (!result.ok) throw new Error(result.diagnostic.message)

    expect(result.view.transcript).toEqual([
      expect.objectContaining({
        type: "interaction",
        id: "active:run-1:interaction:interaction-1",
        interactionId: "interaction-1",
        status: "pending",
        request: expect.objectContaining({
          type: "approval",
          toolName: "bash",
        }),
      }),
    ])
  })

  it("projects a durable plan entry into a stable plan Transcript Block", () => {
    const snapshot = {
      ...emptySnapshotFixture,
      entries: [
        {
          id: "plan-entry-1",
          session_id: "session-1",
          run_id: "run-1",
          sequence: 1,
          schema_version: 1,
          created_at: "2026-08-16T08:00:00.000Z",
          type: "plan",
          payload: {
            plan_id: "plan-1",
            revision: 2,
            title: "Investigate the workflow",
            items: [
              { id: "step-1", text: "Inspect logs", status: "completed" },
              { id: "step-2", text: "Verify outputs", status: "in_progress" },
            ],
            updated_at: "2026-08-16T08:00:01.000Z",
          },
        },
      ],
    }

    const result = createConversationProjection(snapshot)
    if (!result.ok) throw new Error(result.diagnostic.message)

    expect(result.view.transcript).toEqual([
      {
        type: "plan",
        id: "plan-entry-1",
        runId: "run-1",
        createdAt: "2026-08-16T08:00:00.000Z",
        planId: "plan-1",
        revision: 2,
        title: "Investigate the workflow",
        items: [
          { id: "step-1", text: "Inspect logs", status: "completed" },
          { id: "step-2", text: "Verify outputs", status: "in_progress" },
        ],
        updatedAt: "2026-08-16T08:00:01.000Z",
      },
    ])
  })

  it("keeps a failed Run readable as an outcome block", () => {
    const result = createConversationProjection(failedSnapshotFixture)
    if (!result.ok) throw new Error(result.diagnostic.message)

    expect(result.view.transcript).toEqual([
      expect.objectContaining({
        type: "outcome",
        status: "failed",
        reason: "provider_error",
        error: { code: "provider_error", message: "Provider unavailable" },
      }),
    ])
  })

  it("degrades unknown history entries and parts without hiding known content", () => {
    const unknownSnapshot = {
      ...emptySnapshotFixture,
      entries: [
        {
          id: "entry-known",
          session_id: "session-1",
          run_id: "run-1",
          sequence: 1,
          schema_version: 1,
          created_at: "2026-08-16T08:00:00.000Z",
          type: "message",
          payload: {
            role: "assistant",
            parts: [
              { id: "known", type: "text", text: "Still visible" },
              { id: "private", type: "provider_checkpoint", token: "opaque" },
            ],
          },
        },
        {
          id: "entry-unknown",
          session_id: "session-1",
          run_id: "run-1",
          sequence: 2,
          schema_version: 1,
          created_at: "2026-08-16T08:00:01.000Z",
          type: "harness_checkpoint",
          payload: { opaque: true },
        },
      ],
    }

    const result = createConversationProjection(unknownSnapshot)
    if (!result.ok) throw new Error(result.diagnostic.message)

    expect(result.view.transcript).toEqual([
      expect.objectContaining({ type: "message", text: "Still visible" }),
      expect.objectContaining({
        type: "unknown",
        originalType: "provider_checkpoint",
        diagnosticCode: "unknown_message_part",
        diagnosticParams: { originalType: "provider_checkpoint" },
      }),
      expect.objectContaining({
        type: "unknown",
        originalType: "harness_checkpoint",
        diagnosticCode: "unknown_history_entry",
        diagnosticParams: { originalType: "harness_checkpoint" },
      }),
    ])
  })

  it("retains known Conversation content and appends a diagnostic for a newer protocol version", () => {
    const result = createConversationProjection({
      ...emptySnapshotFixture,
      presentation_schema_version: 99,
      entries: [
        {
          id: "entry-known",
          session_id: "session-1",
          run_id: "run-1",
          sequence: 1,
          schema_version: 1,
          created_at: "2026-08-16T08:00:00.000Z",
          type: "message",
          payload: {
            role: "assistant",
            parts: [{ id: "known", type: "text", text: "Still visible" }],
          },
        },
      ],
    })
    if (!result.ok) throw new Error(result.diagnostic.message)

    expect(result.view.protocolVersion).toBe(99)
    expect(result.view.transcript).toEqual([
      expect.objectContaining({ type: "message", text: "Still visible" }),
      expect.objectContaining({
        type: "unknown",
        diagnosticCode: "unsupported_protocol_version",
        diagnosticParams: { version: "99" },
      }),
    ])
  })

  it("coalesces a persisted interaction request and response into one resolved card", () => {
    const snapshot = {
      ...emptySnapshotFixture,
      entries: [
        {
          id: "request-1",
          session_id: "session-1",
          run_id: "run-1",
          sequence: 1,
          schema_version: 1,
          created_at: "2026-08-16T08:00:00.000Z",
          type: "interaction_request",
          payload: {
            interaction_id: "interaction-1",
            request: {
              type: "approval",
              call_id: "call-1",
              tool_name: "bash",
              summary: "Run command",
              input_preview: "echo ok",
              allowed_responses: ["approve", "reject"],
              risk: {
                level: "low",
                effects: [],
                reasons: [],
                affected_resources: [],
              },
            },
          },
        },
        {
          id: "response-1",
          session_id: "session-1",
          run_id: "run-1",
          sequence: 2,
          schema_version: 1,
          created_at: "2026-08-16T08:00:01.000Z",
          type: "interaction_response",
          payload: {
            interaction_id: "interaction-1",
            response: { type: "approval", approved: true },
          },
        },
      ],
    }

    const result = createConversationProjection(snapshot)
    if (!result.ok) throw new Error(result.diagnostic.message)

    expect(result.view.transcript).toEqual([
      expect.objectContaining({
        type: "interaction",
        id: "request-1",
        status: "resolved",
        request: expect.objectContaining({ type: "approval" }),
        response: { type: "approval", approved: true },
      }),
    ])
  })

  it("reconciles tool results committed in later history entries", () => {
    const snapshot = {
      ...emptySnapshotFixture,
      entries: [
        {
          id: "assistant-tools",
          session_id: "session-1",
          run_id: "run-1",
          sequence: 1,
          schema_version: 1,
          created_at: "2026-08-16T08:00:00.000Z",
          type: "message",
          payload: {
            role: "assistant",
            parts: [
              {
                id: "call-part",
                type: "tool_call",
                call_id: "call-1",
                group_id: "group-1",
                execution_mode: "serial",
                name: "read",
                display_name: "Read",
                category: "read",
                summary: "Read file",
                arguments: { path: "README.md" },
              },
            ],
          },
        },
        {
          id: "tool-result",
          session_id: "session-1",
          run_id: "run-1",
          sequence: 2,
          schema_version: 1,
          created_at: "2026-08-16T08:00:01.000Z",
          type: "message",
          payload: {
            role: "tool",
            parts: [
              {
                id: "result-part",
                type: "tool_result",
                call_id: "call-1",
                status: "completed",
                summary: "Read README.md",
                output: { type: "text", text: "BioinfoFlow" },
                started_at: "2026-08-16T08:00:00.000Z",
                completed_at: "2026-08-16T08:00:01.000Z",
                error: null,
              },
            ],
          },
        },
      ],
    }

    const result = createConversationProjection(snapshot)
    if (!result.ok) throw new Error(result.diagnostic.message)

    expect(result.view.transcript).toEqual([
      expect.objectContaining({
        type: "activity_group",
        activities: [
          expect.objectContaining({
            callId: "call-1",
            status: "completed",
            summary: "Read file",
            output: { type: "text", text: "BioinfoFlow" },
          }),
        ],
      }),
    ])
  })

  it("accepts the current presentation envelope and schema-v2 reasoning trace", () => {
    const snapshot = {
      ...emptySnapshotFixture,
      presentation_protocol: "bioinfoflow.agent.presentation",
      presentation_schema_version: 1,
      entries: [
        {
          id: "reasoning-entry",
          session_id: "session-1",
          run_id: "run-1",
          sequence: 1,
          schema_version: 2,
          created_at: "2026-08-16T08:00:00.000Z",
          type: "message",
          payload: {
            role: "assistant",
            parts: [
              {
                id: "trace-1",
                type: "reasoning_trace",
                text: "Inspect the failing invariant.",
                provider: "openai",
                model: "gpt-5.6",
                source: "reasoning_content",
                truncated: true,
                started_at: null,
                completed_at: null,
              },
            ],
          },
        },
      ],
    }

    const result = createConversationProjection(snapshot)
    if (!result.ok) throw new Error(result.diagnostic.message)

    expect(result.view.transcript).toEqual([
      expect.objectContaining({
        type: "reasoning",
        text: "Inspect the failing invariant.",
        provider: "openai",
        model: "gpt-5.6",
        sourceField: "reasoning_content",
        truncated: true,
      }),
    ])
  })
})
