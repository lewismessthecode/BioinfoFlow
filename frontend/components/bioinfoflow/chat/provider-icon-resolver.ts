export type ProviderIconIdentity = {
  provider: string
  providerLabel?: string | null
  baseUrl?: string | null
  modelId?: string | null
  modelName?: string | null
}

export type ProviderIconKey =
  | "anthropic"
  | "custom"
  | "deepseek"
  | "gemini"
  | "kimi"
  | "minimax"
  | "ollama"
  | "openai"
  | "openrouter"
  | "qwen"
  | "xai"

const DIRECT_ALIASES: Record<string, ProviderIconKey> = {
  anthropic: "anthropic",
  claude: "anthropic",
  deepseek: "deepseek",
  gemini: "gemini",
  google: "gemini",
  kimi: "kimi",
  minimax: "minimax",
  ollama: "ollama",
  openai: "openai",
  openrouter: "openrouter",
  qwen: "qwen",
  tongyi: "qwen",
  xai: "xai",
  "x-ai": "xai",
  grok: "xai",
}

const COMPATIBLE_PROVIDER_KEYS = new Set([
  "openai_compatible",
  "openai-compatible",
  "compatible",
  "vllm",
])

export function resolveProviderIconKey({
  provider,
  providerLabel,
  baseUrl,
  modelId,
  modelName,
}: ProviderIconIdentity): ProviderIconKey {
  const providerKey = normalize(provider)
  const direct = DIRECT_ALIASES[providerKey]
  if (direct) return direct

  const candidateTexts = [
    baseUrl,
    modelId,
    modelName,
    isGenericCompatibleLabel(providerLabel) ? null : providerLabel,
  ]

  for (const candidate of candidateTexts) {
    const inferred = inferBrandFromText(candidate ?? "")
    if (inferred) return inferred
  }

  return COMPATIBLE_PROVIDER_KEYS.has(providerKey) ? "custom" : "custom"
}

function inferBrandFromText(value: string): ProviderIconKey | null {
  const text = normalize(value)
  if (!text) return null
  if (/anthropic|claude/.test(text)) return "anthropic"
  if (/deepseek/.test(text)) return "deepseek"
  if (/gemini|google/.test(text)) return "gemini"
  if (/openrouter/.test(text)) return "openrouter"
  if (/qwen|tongyi/.test(text)) return "qwen"
  if (/kimi/.test(text)) return "kimi"
  if (/minimax/.test(text)) return "minimax"
  if (/ollama|localhost:11434|127\.0\.0\.1:11434/.test(text)) return "ollama"
  if (/(^|[^a-z0-9])(gpt|chatgpt|o1|o3|o4)([^a-z0-9]|$)/.test(text)) return "openai"
  if (/openai|api\.openai\.com/.test(text)) return "openai"
  if (/grok|xai|x-ai/.test(text)) return "xai"
  return null
}

function isGenericCompatibleLabel(value?: string | null) {
  const label = normalize(value ?? "")
  return [
    "compatible",
    "openai-compatible",
    "openai-compatible-api",
    "openai-compatible-endpoint",
    "openai-api-compatible",
  ].includes(label)
}

function normalize(value: string) {
  return value.trim().toLowerCase().replace(/[\s/_]+/g, "-")
}
