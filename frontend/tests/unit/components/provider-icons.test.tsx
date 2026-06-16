import { describe, expect, it } from "vitest"

import { resolveProviderIconKey } from "@/components/bioinfoflow/chat/provider-icon-resolver"

describe("resolveProviderIconKey", () => {
  it("uses direct provider brand aliases", () => {
    expect(resolveProviderIconKey({ provider: "openai" })).toBe("openai")
    expect(resolveProviderIconKey({ provider: "anthropic" })).toBe("anthropic")
    expect(resolveProviderIconKey({ provider: "claude" })).toBe("anthropic")
    expect(resolveProviderIconKey({ provider: "google" })).toBe("gemini")
    expect(resolveProviderIconKey({ provider: "grok" })).toBe("xai")
  })

  it("infers compatible endpoint branding from provider labels and model names", () => {
    expect(
      resolveProviderIconKey({
        provider: "openai_compatible",
        providerLabel: "DeepSeek Gateway",
        modelId: "deepseek-reasoner",
      }),
    ).toBe("deepseek")
    expect(
      resolveProviderIconKey({
        provider: "vllm",
        providerLabel: "Local vLLM",
        modelId: "claude-3-5-sonnet",
      }),
    ).toBe("anthropic")
    expect(
      resolveProviderIconKey({
        provider: "openai_compatible",
        providerLabel: "Custom GPT endpoint",
        modelName: "GPT-4o",
      }),
    ).toBe("openai")
  })

  it("keeps unknown vLLM and OpenAI-compatible endpoints neutral", () => {
    expect(
      resolveProviderIconKey({
        provider: "openai_compatible",
        providerLabel: "OpenAI Compatible",
        modelId: "lab-model-v2",
      }),
    ).toBe("custom")
    expect(
      resolveProviderIconKey({
        provider: "openai_compatible",
        providerLabel: "Private API",
        modelId: "lab-model-v2",
      }),
    ).toBe("custom")
    expect(
      resolveProviderIconKey({
        provider: "vllm",
        providerLabel: "Local vLLM",
        modelId: "lab-model-v2",
      }),
    ).toBe("custom")
  })

  it("infers compatible endpoint branding from base URLs", () => {
    expect(
      resolveProviderIconKey({
        provider: "openai_compatible",
        providerLabel: "OpenAI Compatible",
        baseUrl: "https://api.deepseek.com/v1",
        modelId: "lab-model-v2",
      }),
    ).toBe("deepseek")
    expect(
      resolveProviderIconKey({
        provider: "openai_compatible",
        providerLabel: "OpenAI Compatible",
        baseUrl: "http://localhost:11434/v1",
        modelId: "lab-model-v2",
      }),
    ).toBe("ollama")
    expect(
      resolveProviderIconKey({
        provider: "vllm",
        providerLabel: "Local vLLM",
        baseUrl: "https://api.openai.com/v1",
        modelId: "lab-model-v2",
      }),
    ).toBe("openai")
  })

  it("recognizes common Qwen model id variants", () => {
    expect(
      resolveProviderIconKey({
        provider: "openai_compatible",
        providerLabel: "OpenAI Compatible",
        modelId: "qwen3-coder",
      }),
    ).toBe("qwen")
    expect(
      resolveProviderIconKey({
        provider: "vllm",
        providerLabel: "Local vLLM",
        modelName: "Qwen2.5 Coder",
      }),
    ).toBe("qwen")
  })
})
