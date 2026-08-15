import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { resolveProviderIconKey } from "@/components/bioinfoflow/chat/provider-icon-resolver"
import { ProviderIcon } from "@/components/bioinfoflow/chat/provider-icons"

describe("resolveProviderIconKey", () => {
  it("uses direct provider brand aliases", () => {
    const aliases = [
      ["openai", "openai"],
      ["anthropic", "anthropic"],
      ["claude", "anthropic"],
      ["azure", "azure"],
      ["openrouter", "openrouter"],
      ["fireworks", "fireworks"],
      ["qwen", "qwen"],
      ["deepseek", "deepseek"],
      ["xai", "xai"],
      ["grok", "xai"],
      ["zai", "zai"],
      ["kimi", "kimi"],
      ["kimi_cn", "kimi"],
      ["kimi_code", "kimi"],
      ["minimax", "minimax"],
      ["huggingface", "huggingface"],
      ["gemini", "gemini"],
      ["google", "gemini"],
      ["groq", "groq"],
      ["mistral", "mistral"],
      ["cohere", "cohere"],
      ["together", "together"],
      ["perplexity", "perplexity"],
      ["ollama", "ollama"],
    ] as const

    for (const [provider, expected] of aliases) {
      expect(resolveProviderIconKey({ provider })).toBe(expected)
    }
  })

  it("uses theme-aware monochrome artwork for provider logos", () => {
    render(<ProviderIcon provider="kimi" />)

    expect(screen.getByTitle("Kimi").closest("svg")).toHaveAttribute(
      "fill",
      "currentColor",
    )
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
