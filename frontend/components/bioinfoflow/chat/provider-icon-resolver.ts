export type ProviderIconIdentity = {
  provider: string
  providerLabel?: string | null
  baseUrl?: string | null
  modelId?: string | null
  modelName?: string | null
}

export type ProviderIconKey =
  | "anthropic"
  | "azure"
  | "cohere"
  | "custom"
  | "deepseek"
  | "fireworks"
  | "gemini"
  | "groq"
  | "huggingface"
  | "kimi"
  | "minimax"
  | "mistral"
  | "ollama"
  | "openai"
  | "openrouter"
  | "perplexity"
  | "qwen"
  | "together"
  | "xai"
  | "zai"

const DIRECT_ALIASES: Record<string, ProviderIconKey> = {
  anthropic: "anthropic",
  azure: "azure",
  claude: "anthropic",
  cohere: "cohere",
  deepseek: "deepseek",
  fireworks: "fireworks",
  gemini: "gemini",
  google: "gemini",
  groq: "groq",
  huggingface: "huggingface",
  "hugging-face": "huggingface",
  kimi: "kimi",
  "kimi-cn": "kimi",
  "kimi-code": "kimi",
  moonshot: "kimi",
  minimax: "minimax",
  mistral: "mistral",
  ollama: "ollama",
  openai: "openai",
  openrouter: "openrouter",
  perplexity: "perplexity",
  qwen: "qwen",
  together: "together",
  tongyi: "qwen",
  xai: "xai",
  "x-ai": "xai",
  grok: "xai",
  zai: "zai",
  "z-ai": "zai",
  zhipu: "zai",
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
  if (/azure/.test(text)) return "azure"
  if (/cohere/.test(text)) return "cohere"
  if (/deepseek/.test(text)) return "deepseek"
  if (/fireworks/.test(text)) return "fireworks"
  if (/gemini|google/.test(text)) return "gemini"
  if (/groq/.test(text)) return "groq"
  if (/huggingface|hugging-face/.test(text)) return "huggingface"
  if (/openrouter/.test(text)) return "openrouter"
  if (/perplexity|pplx/.test(text)) return "perplexity"
  if (/qwen|tongyi/.test(text)) return "qwen"
  if (/kimi|moonshot/.test(text)) return "kimi"
  if (/minimax/.test(text)) return "minimax"
  if (/mistral/.test(text)) return "mistral"
  if (/ollama|localhost:11434|127\.0\.0\.1:11434/.test(text)) return "ollama"
  if (/together/.test(text)) return "together"
  if (/(^|[^a-z0-9])(gpt|chatgpt|o1|o3|o4)([^a-z0-9]|$)/.test(text)) return "openai"
  if (/openai|api\.openai\.com/.test(text)) return "openai"
  if (/grok|xai|x-ai/.test(text)) return "xai"
  if (/zai|z-ai|zhipu|bigmodel/.test(text)) return "zai"
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
