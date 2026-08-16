import { describe, expect, it } from "vitest"

import {
  editDraftFromUserMessage,
  retryInputPartsForAssistant,
} from "@/lib/agent/transcript"
import type { MessageEntry } from "@/lib/agent/contracts"

function message(
  id: string,
  sequence: number,
  role: "user" | "assistant",
  parts: MessageEntry["payload"]["parts"],
): MessageEntry {
  return {
    id,
    type: "message",
    sequence,
    run_id: "run-1",
    created_at: `2026-08-16T08:00:0${sequence}Z`,
    schema_version: 1,
    payload: { role, parts },
  }
}

describe("agent transcript input derivation", () => {
  it("reconstructs typed retry input from the canonical user entry", () => {
    const user = message("user-1", 1, "user", [
      { id: "text-1", type: "text", text: "Inspect this run" },
      { id: "run-ref", type: "run_ref", run_id: "run-42", label: "Run 42" },
    ])
    const assistant = message("assistant-1", 2, "assistant", [
      { id: "text-2", type: "text", text: "Here is the result" },
    ])

    expect(retryInputPartsForAssistant([user, assistant], assistant)).toEqual([
      { type: "text", text: "Inspect this run" },
      { type: "run_ref", run_id: "run-42" },
    ])
  })

  it("creates an editable draft without mutating durable message parts", () => {
    const user = message("user-1", 1, "user", [
      { id: "text-1", type: "text", text: "Compare these files" },
      {
        id: "file-ref",
        type: "file_ref",
        label: "counts.tsv",
        project_id: "project-1",
        path: "results/counts.tsv",
      },
    ])

    expect(editDraftFromUserMessage(user)).toEqual({
      text: "Compare these files",
      contextInputs: [
        {
          id: "file-ref",
          kind: "file",
          label: "counts.tsv",
          detail: "results/counts.tsv",
          input_part: {
            type: "file_ref",
            project_id: "project-1",
            path: "results/counts.tsv",
          },
        },
      ],
    })
    expect(user.payload.parts).toHaveLength(2)
  })
})
