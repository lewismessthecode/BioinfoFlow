import type {
  ModelSelection,
  ProviderModels,
} from "@/hooks/use-llm-settings"

import type {
  ConversationModelSelection,
  ConversationSettings,
} from "./types"

/** Keeps catalog wire fields outside the Conversation UI contract. */
export function conversationModelSelectionFromCatalog(
  selection: ModelSelection | null,
): ConversationModelSelection | null {
  if (!selection) return null
  if (selection.model_id) return { modelId: selection.model_id }
  return selection.provider && selection.model
    ? { provider: selection.provider, model: selection.model }
    : null
}

export function catalogModelSelectionFromConversation(
  conversationModel: ConversationSettings["model"] | null,
  models: readonly ProviderModels[],
): ModelSelection {
  const directProvider = models.find(
    (group) =>
      group.provider === conversationModel?.provider &&
      group.models.some((candidate) => candidate.id === conversationModel?.model),
  )
  const compatibleProviders = models.filter(
    (group) =>
      group.provider_kind === conversationModel?.provider &&
      group.models.some((candidate) => candidate.id === conversationModel?.model),
  )
  const provider =
    directProvider ??
    (compatibleProviders.length === 1 ? compatibleProviders[0] : undefined)
  const selectedModel = provider?.models.find(
    (candidate) => candidate.id === conversationModel?.model,
  )
  return {
    provider: provider?.provider ?? conversationModel?.provider ?? "",
    model: conversationModel?.model ?? "",
    model_id: selectedModel?.model_id ?? null,
  }
}

export function catalogModelSelectionEquals(
  left: ModelSelection,
  right: ModelSelection,
) {
  if (left.model_id && right.model_id) return left.model_id === right.model_id
  return left.provider === right.provider && left.model === right.model
}
