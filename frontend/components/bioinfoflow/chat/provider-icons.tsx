/**
 * Provider icon wrapper around @lobehub/icons.
 *
 * Maps provider keys to the corresponding LobeHub brand icons.
 * Uses the `.Color` variant when available for rich brand colors;
 * falls back to `Mono` (adapts to currentColor for dark/light mode).
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
  Claude,
  DeepSeek,
  Gemini,
  Grok,
  Kimi,
  Minimax,
  Ollama,
  OpenAI,
  OpenRouter,
  Qwen,
  XAI,
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

interface IconEntry {
  Color?: IconComponent
  Mono: IconComponent
}

// ── Icon registry ──────────────────────────────────────────────────
// Keys must match the `provider` string returned by the backend API.

const PROVIDER_ICON_MAP: Record<string, IconEntry> = {
  anthropic:   { Color: Claude.Color, Mono: Claude },
  custom:      { Mono: Server },
  openai:      { Mono: OpenAI },
  gemini:      { Color: Gemini.Color, Mono: Gemini },
  ollama:      { Mono: Ollama },
  qwen:        { Color: Qwen.Color, Mono: Qwen },
  deepseek:    { Color: DeepSeek.Color, Mono: DeepSeek },
  kimi:        { Color: Kimi.Color, Mono: Kimi },
  minimax:     { Color: Minimax.Color, Mono: Minimax },
  xai:         { Color: XAI.Color, Mono: Grok },
  openrouter:  { Color: OpenRouter.Color, Mono: OpenRouter },
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
  const entry = PROVIDER_ICON_MAP[key]

  if (!entry) {
    return (
      <span
        className={cn("inline-block shrink-0 text-muted-foreground/60", className)}
        style={{ fontSize: size, lineHeight: 1 }}
        aria-hidden="true"
      >
        ○
      </span>
    )
  }

  // Prefer Color variant; fall back to Mono
  const Icon = entry.Color ?? entry.Mono
  return <Icon size={size} className={cn("shrink-0", className)} />
}
