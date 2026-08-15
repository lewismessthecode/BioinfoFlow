/**
 * Provider icon wrapper around @lobehub/icons.
 *
 * Maps provider keys to the corresponding LobeHub brand icons.
 * Uses monochrome artwork so every logo follows `currentColor` and remains
 * visible on both light and dark composer surfaces.
 *
 * ┌─────────────────────────────────────────────────────────────────┐
 * │  To add a new provider:                                        │
 * │  1. Import its leaf Mono component from "@lobehub/icons"       │
 * │  2. Add an entry to PROVIDER_ICON_MAP below                    │
 * │  3. Add a label in PROVIDER_LABELS in model-selector.tsx       │
 * │                                                                │
 * │  That's it — the model list comes from the backend API.        │
 * └─────────────────────────────────────────────────────────────────┘
 */

import Anthropic from "@lobehub/icons/es/Anthropic/components/Mono.js"
import Azure from "@lobehub/icons/es/Azure/components/Mono.js"
import Cohere from "@lobehub/icons/es/Cohere/components/Mono.js"
import DeepSeek from "@lobehub/icons/es/DeepSeek/components/Mono.js"
import Fireworks from "@lobehub/icons/es/Fireworks/components/Mono.js"
import Gemini from "@lobehub/icons/es/Gemini/components/Mono.js"
import Groq from "@lobehub/icons/es/Groq/components/Mono.js"
import HuggingFace from "@lobehub/icons/es/HuggingFace/components/Mono.js"
import Kimi from "@lobehub/icons/es/Kimi/components/Mono.js"
import Minimax from "@lobehub/icons/es/Minimax/components/Mono.js"
import Mistral from "@lobehub/icons/es/Mistral/components/Mono.js"
import Ollama from "@lobehub/icons/es/Ollama/components/Mono.js"
import OpenAI from "@lobehub/icons/es/OpenAI/components/Mono.js"
import OpenRouter from "@lobehub/icons/es/OpenRouter/components/Mono.js"
import Perplexity from "@lobehub/icons/es/Perplexity/components/Mono.js"
import Qwen from "@lobehub/icons/es/Qwen/components/Mono.js"
import Together from "@lobehub/icons/es/Together/components/Mono.js"
import XAI from "@lobehub/icons/es/XAI/components/Mono.js"
import ZAI from "@lobehub/icons/es/ZAI/components/Mono.js"
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
