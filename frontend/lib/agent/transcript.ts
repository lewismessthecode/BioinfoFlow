import type {
  HistoryEntry,
  InputPart,
  MessageEntry,
  MessagePart,
} from "@/lib/agent/contracts"
import type { AgentContextInput } from "@/lib/agent/context"

export function retryInputPartsForAssistant(
  entries: HistoryEntry[],
  assistant: MessageEntry,
): InputPart[] {
  if (assistant.payload.role !== "assistant" || !assistant.run_id) return []
  const source = entries
    .filter(
      (entry): entry is MessageEntry =>
        entry.type === "message" &&
        entry.payload.role === "user" &&
        entry.run_id === assistant.run_id &&
        entry.sequence < assistant.sequence,
    )
    .toSorted((left, right) => right.sequence - left.sequence)[0]
  return source ? inputPartsFromMessage(source) : []
}

function inputPartsFromMessage(entry: MessageEntry): InputPart[] {
  if (entry.payload.role !== "user") return []
  return entry.payload.parts.flatMap(inputPartFromMessagePart)
}

export function editDraftFromUserMessage(entry: MessageEntry): {
  text: string
  contextInputs: AgentContextInput[]
} {
  if (entry.payload.role !== "user") return { text: "", contextInputs: [] }
  const text = entry.payload.parts
    .flatMap((part) => (part.type === "text" ? [part.text.trim()] : []))
    .filter(Boolean)
    .join("\n\n")
  return {
    text,
    contextInputs: entry.payload.parts.flatMap(contextInputFromMessagePart),
  }
}

function inputPartFromMessagePart(part: MessagePart): InputPart[] {
  switch (part.type) {
    case "text":
      return part.text.trim() ? [{ type: "text", text: part.text }] : []
    case "attachment_ref":
      return [{ type: "attachment_ref", attachment_id: part.attachment_id }]
    case "file_ref":
      return fileOrDirectoryInput(part, "file_ref")
    case "directory_ref":
      return fileOrDirectoryInput(part, "directory_ref")
    case "workflow_ref":
      return [
        part.project_id
          ? {
              type: "workflow_ref",
              workflow_id: part.workflow_id,
              scope: "project",
              project_id: part.project_id,
            }
          : {
              type: "workflow_ref",
              workflow_id: part.workflow_id,
              scope: "global",
            },
      ]
    case "run_ref":
      return [{ type: "run_ref", run_id: part.run_id }]
    default:
      return []
  }
}

function fileOrDirectoryInput(
  part: Extract<MessagePart, { type: "file_ref" | "directory_ref" }>,
  type: "file_ref" | "directory_ref",
): InputPart[] {
  if (part.attachment_id) return [{ type, attachment_id: part.attachment_id }]
  if (part.project_id && part.path) {
    return [{ type, project_id: part.project_id, path: part.path }]
  }
  return []
}

function contextInputFromMessagePart(part: MessagePart): AgentContextInput[] {
  const inputPart = inputPartFromMessagePart(part)[0]
  if (!inputPart || inputPart.type === "text") return []
  switch (part.type) {
    case "attachment_ref":
      return [{
        id: part.id,
        kind: "attachment",
        label: part.filename,
        detail: part.mime_type,
        input_part: inputPart,
      }]
    case "file_ref":
    case "directory_ref":
      return [{
        id: part.id,
        kind: part.type === "file_ref" ? "file" : "directory",
        label: part.label,
        detail: part.path ?? null,
        input_part: inputPart,
      }]
    case "workflow_ref":
      return [{
        id: part.id,
        kind: "workflow",
        label: part.label,
        detail: null,
        input_part: inputPart,
      }]
    case "run_ref":
      return [{
        id: part.id,
        kind: "run",
        label: part.label,
        detail: part.run_id,
        input_part: inputPart,
      }]
    default:
      return []
  }
}
