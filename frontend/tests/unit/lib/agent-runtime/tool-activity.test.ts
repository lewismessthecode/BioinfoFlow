import { describe, expect, it } from "vitest"

import {
  buildAgentRuntimeToolActivities,
  type AgentRuntimeEvent,
} from "@/lib/agent-runtime"

const actionEvent = (
  id: string,
  seq: number,
  payload: Record<string, unknown>,
): AgentRuntimeEvent => ({
  id,
  session_id: "session-1",
  turn_id: "turn-1",
  seq,
  type: "action.completed",
  payload,
  visibility: "user",
  schema_version: 1,
  created_at: "2026-06-08T00:00:00Z",
  updated_at: "2026-06-08T00:00:00Z",
})

describe("buildAgentRuntimeToolActivities", () => {
  it("previews structured collaboration tool results", () => {
    const [activity] = buildAgentRuntimeToolActivities([
      actionEvent("event-collab", 1, {
        action_id: "action-collab",
        name: "spawn_agent",
        result: {
          child_session_id: "child-1",
          task_name: "/root/reader",
          status: "pending_init",
          effective_model: "cheap-model",
        },
      }),
    ])

    expect(activity.outputPreview).toContain("/root/reader")
    expect(activity.outputPreview).toContain("pending_init")
    expect(activity.outputPreview).toContain("cheap-model")
  })
  it("uses nested remote action results for command previews after artifacts are filtered", () => {
    const activities = buildAgentRuntimeToolActivities([
      actionEvent("event-exec", 1, {
        action_id: "exec-1",
        name: "remote_exec",
        result: {
          result: {
            stdout: "nextflow run completed",
            exit_code: 0,
          },
        },
      }),
      actionEvent("event-read", 2, {
        action_id: "read-1",
        name: "remote_read",
        result: {
          result: {
            stdout: "sample_id,condition",
            exit_code: 0,
          },
        },
      }),
      actionEvent("event-list", 3, {
        action_id: "list-1",
        name: "remote_list",
        result: {
          result: {
            stderr: "permission denied",
            exit_code: 13,
          },
        },
      }),
    ])

    expect(activities).toEqual([
      expect.objectContaining({
        actionId: "exec-1",
        outputPreview: "nextflow run completed",
        exitCode: 0,
      }),
      expect.objectContaining({
        actionId: "read-1",
        outputPreview: "sample_id,condition",
        exitCode: 0,
      }),
      expect.objectContaining({
        actionId: "list-1",
        outputPreview: "permission denied",
        exitCode: 13,
        status: "failed",
      }),
    ])
  })

  it("keeps top-level action results as the display source", () => {
    const activities = buildAgentRuntimeToolActivities([
      actionEvent("event-local", 1, {
        action_id: "local-1",
        name: "bash",
        result: {
          stdout: "local output",
          exit_code: 0,
          result: {
            stdout: "remote wrapper output",
            exit_code: 99,
          },
        },
      }),
    ])

    expect(activities[0]).toEqual(
      expect.objectContaining({
        actionId: "local-1",
        outputPreview: "local output",
        exitCode: 0,
      }),
    )
  })

  it("treats a nonzero top-level command exit as failed in historical completed events", () => {
    const activities = buildAgentRuntimeToolActivities([
      actionEvent("event-local", 1, {
        action_id: "local-1",
        name: "bash",
        result: {
          stderr: "command failed",
          exit_code: 7,
        },
      }),
    ])

    expect(activities[0]).toEqual(
      expect.objectContaining({
        actionId: "local-1",
        outputPreview: "command failed",
        exitCode: 7,
        status: "failed",
      }),
    )
  })
})
