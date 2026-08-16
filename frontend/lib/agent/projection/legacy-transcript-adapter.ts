import type {
  ActivityGroupTranscriptBlock,
  ActivityItem,
  InteractionTranscriptBlock,
  PlanTranscriptBlock,
  ReasoningTranscriptBlock,
} from "@/lib/agent/conversation-model/types"
import type {
  AssistantDraftPartView,
  InteractionRequest,
  InteractionResponse,
  PlanEntry,
  ToolExecutionMode,
  ToolProgressView,
} from "@/lib/agent/contracts"

export function activityFromToolProgress(tool: ToolProgressView): ActivityItem {
  return {
    id: tool.call_id,
    callId: tool.call_id,
    name: tool.name,
    displayName: tool.display_name,
    category: tool.category,
    summary: tool.summary,
    status: tool.status,
    input: tool.arguments,
    output: tool.output_summary,
    error: tool.error,
    startedAt: tool.started_at,
    completedAt: tool.completed_at,
    details: (tool.public_details ?? []).map((detail) => ({
      id: detail.id,
      kind: detail.kind,
      label: detail.label,
      value: detail.value,
      format: detail.format,
      copyable: detail.copyable,
      truncated: detail.truncated,
      redacted: detail.redacted,
    })),
  }
}

export function activityGroupFromToolProgress(
  tools: ToolProgressView[],
  executionMode?: ToolExecutionMode,
): ActivityGroupTranscriptBlock {
  return {
    type: "activity_group",
    id: `legacy:activity:${tools.map((tool) => tool.call_id).join(":")}`,
    runId: null,
    createdAt: tools[0]?.started_at ?? null,
    executionMode: executionMode ?? commonExecutionMode(tools),
    activities: tools.map(activityFromToolProgress),
  }
}

export function reasoningFromDraftPart(
  part: Pick<AssistantDraftPartView, "id" | "text">,
  streaming: boolean,
): ReasoningTranscriptBlock {
  return {
    type: "reasoning",
    id: `legacy:reasoning:${part.id}`,
    runId: null,
    createdAt: null,
    text: part.text,
    streaming,
    provider: null,
    model: null,
    sourceField: "reasoning_summary",
    truncated: false,
    startedAt: null,
    completedAt: null,
    durationMs: null,
  }
}

export function interactionFromLegacy(
  interactionId: string,
  request: InteractionRequest,
  response: InteractionResponse | null = null,
): InteractionTranscriptBlock {
  return {
    type: "interaction",
    id: `legacy:interaction:${interactionId}`,
    runId: null,
    createdAt: null,
    interactionId,
    status: response ? "resolved" : "pending",
    request: projectInteractionRequest(request),
    response,
  }
}

export function planFromLegacy(entry: Pick<PlanEntry, "id" | "run_id" | "created_at" | "payload">): PlanTranscriptBlock {
  return {
    type: "plan",
    id: entry.id,
    runId: entry.run_id,
    createdAt: entry.created_at,
    planId: entry.payload.plan_id,
    revision: entry.payload.revision,
    title: entry.payload.title ?? null,
    items: entry.payload.items,
    updatedAt: entry.payload.updated_at,
  }
}

function projectInteractionRequest(
  request: InteractionRequest,
): InteractionTranscriptBlock["request"] {
  if (request.type === "approval") {
    return {
      type: "approval",
      callId: request.call_id,
      toolName: request.tool_name,
      summary: request.summary,
      inputPreview: request.input_preview,
      allowedResponses: request.allowed_responses,
      risk: {
        level: request.risk.level,
        effects: request.risk.effects,
        reasons: request.risk.reasons,
        affectedResources: request.risk.affected_resources,
      },
      target: null,
    }
  }
  if (request.type === "ask_user") {
    return {
      type: "ask_user",
      callId: request.call_id,
      questions: request.questions.map((question) => ({
        id: question.id,
        header: question.header,
        question: question.question,
        multiSelect: question.multi_select,
        options: question.options,
      })),
    }
  }
  return {
    type: "recovery",
    callId: request.call_id,
    toolName: request.tool_name,
    messageCode: request.message_code ?? null,
    messageParams: Object.fromEntries(
      Object.entries(request.message_params ?? {}).filter(
        (entry): entry is [string, string | number] =>
          typeof entry[1] === "string" || typeof entry[1] === "number",
      ),
    ),
    messageFallback: request.message,
    options: request.options,
  }
}

function commonExecutionMode(tools: ToolProgressView[]) {
  const first = tools[0]?.execution_mode
  if (!first) return "mixed"
  return tools.every((tool) => tool.execution_mode === first) ? first : "mixed"
}
