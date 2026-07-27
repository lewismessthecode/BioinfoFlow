/**
 * Provider icon wrapper around @lobehub/icons.
 *
 * Maps provider keys to the corresponding LobeHub brand icons.
 * Uses monochrome artwork so every logo follows `currentColor` and remains
 * visible on both light and dark composer surfaces.
 *
 * ┌─────────────────────────────────────────────────────────────────┐
 * │  To add a new provider:                                        │
 * │  1. Import the icon from "@lobehub/icons"                      │
 * │  2. Add an entry to PROVIDER_ICON_MAP below                    │
 * │  3. Add a label in PROVIDER_LABELS in model-selector.tsx       │
 * │                                                                │
 * │  That's it — the model list comes from the backend API.        │
 * └─────────────────────────────────────────────────────────────────┘
 */

import {
  Anthropic,
  Azure,
  Cohere,
  DeepSeek,
  Fireworks,
  Gemini,
  Groq,
  HuggingFace,
  Kimi,
  Minimax,
  Mistral,
  Ollama,
  OpenAI,
  OpenRouter,
  Perplexity,
  Qwen,
  Together,
  XAI,
  ZAI,
} from "@lobehub/icons"
import { Server } from "@/lib/icons"
import { cn } from "@/lib/utils"
import {
  resolveProviderIconKey,
  type ProviderIconIdentity,
} from "./provider-icon-resolver"

// ── Types ──────────────────────────────────────────────────────────

interface ProviderIconProps {
  provider: string
  providerLabel?: string | null
  baseUrl?: string | null
  modelId?: string | null
  modelName?: string | null
  className?: string
  size?: number
}

type IconComponent = React.ComponentType<{ size?: number; className?: string }>

// ── Icon registry ──────────────────────────────────────────────────
// Keys must match the `provider` string returned by the backend API.

const PROVIDER_ICON_MAP: Record<
  ReturnType<typeof resolveProviderIconKey>,
  IconComponent
> = {
  anthropic: Anthropic,
  azure: Azure,
  cohere: Cohere,
  custom: Server,
  deepseek: DeepSeek,
  fireworks: Fireworks,
  gemini: Gemini,
  groq: Groq,
  huggingface: HuggingFace,
  kimi: Kimi,
  minimax: Minimax,
  mistral: Mistral,
  ollama: Ollama,
  openai: OpenAI,
  openrouter: OpenRouter,
  perplexity: Perplexity,
  qwen: Qwen,
  together: Together,
  xai: XAI,
  zai: ZAI,
}

// ── Component ──────────────────────────────────────────────────────

export function ProviderIcon({
  provider,
  providerLabel,
  baseUrl,
  modelId,
  modelName,
  className,
  size = 14,
}: ProviderIconProps) {
  const key = resolveProviderIconKey({
    provider,
    providerLabel,
    baseUrl,
    modelId,
    modelName,
  } satisfies ProviderIconIdentity)
  const Icon = PROVIDER_ICON_MAP[key]
  return <Icon size={size} className={cn("shrink-0", className)} />
}
