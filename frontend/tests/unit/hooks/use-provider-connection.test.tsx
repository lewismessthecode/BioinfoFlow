import { act, renderHook } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { useProviderConnection } from "@/hooks/use-provider-connection"

const provider = {
  id: "provider-openai",
  name: "OpenAI",
  kind: "openai",
} as const

const model = {
  id: "model-gpt",
  provider_id: provider.id,
  model_id: "gpt-5.4-mini",
  display_name: "GPT-5.4 Mini",
  supports_tools: true,
} as const

function operations(overrides: Record<string, unknown> = {}) {
  return {
    setupProvider: vi.fn().mockResolvedValue({
      ok: true,
      result: { provider, models: [model], discovered: false },
    }),
    discoverModels: vi.fn().mockResolvedValue([model]),
    testProvider: vi.fn().mockResolvedValue({
      provider_id: provider.id,
      success: true,
      model: model.model_id,
      error: null,
    }),
    activation: {
      mode: "activate" as const,
      setSelectedModel: vi.fn().mockResolvedValue(undefined),
      refreshSettings: vi.fn().mockResolvedValue(undefined),
    },
    ...overrides,
  }
}

describe("useProviderConnection", () => {
  it("sets up, probes, selects, and refreshes a provider without discovery", async () => {
    const deps = operations()
    const { result } = renderHook(() => useProviderConnection(deps))

    let outcome: Awaited<ReturnType<typeof result.current.connect>> | undefined
    await act(async () => {
      outcome = await result.current.connect({
        templateId: "openai",
        apiKey: "sk-test",
      })
    })

    expect(deps.setupProvider).toHaveBeenCalledWith({
      templateId: "openai",
      apiKey: "sk-test",
      discover: false,
    })
    expect(deps.discoverModels).not.toHaveBeenCalled()
    expect(deps.testProvider).toHaveBeenCalledWith(provider.id, model.id)
    expect(deps.activation.setSelectedModel).toHaveBeenCalledWith({
      provider: provider.id,
      model: model.model_id,
      model_id: model.id,
    })
    expect(deps.activation.refreshSettings).toHaveBeenCalledOnce()
    expect(outcome).toEqual({
      ok: true,
      providerId: provider.id,
      modelId: model.id,
      modelName: model.model_id,
    })
  })

  it("returns setup failures without a provider id", async () => {
    const error = new Error("credential rejected")
    const deps = operations({
      setupProvider: vi.fn().mockResolvedValue({ ok: false, error }),
    })
    const { result } = renderHook(() => useProviderConnection(deps))

    let outcome
    await act(async () => {
      outcome = await result.current.connect({ templateId: "openai" })
    })

    expect(outcome).toEqual({ ok: false, stage: "setup", error })
  })

  it("returns a model failure when setup returns no models", async () => {
    const deps = operations({
      setupProvider: vi.fn().mockResolvedValue({
        ok: true,
        result: { provider, models: [], discovered: false },
      }),
    })
    const { result } = renderHook(() => useProviderConnection(deps))

    let outcome
    await act(async () => {
      outcome = await result.current.connect({ templateId: "openai" })
    })

    expect(outcome).toMatchObject({
      ok: false,
      stage: "model",
      providerId: provider.id,
    })
    expect(deps.discoverModels).not.toHaveBeenCalled()
  })

  it("returns a model failure when setup models are not tool capable", async () => {
    const deps = operations({
      setupProvider: vi.fn().mockResolvedValue({
        ok: true,
        result: {
          provider,
          models: [{ ...model, supports_tools: false }],
          discovered: false,
        },
      }),
    })
    const { result } = renderHook(() => useProviderConnection(deps))

    let outcome
    await act(async () => {
      outcome = await result.current.connect({ templateId: "openai" })
    })

    expect(outcome).toMatchObject({
      ok: false,
      stage: "model",
      providerId: provider.id,
    })
    expect(deps.testProvider).not.toHaveBeenCalled()
  })

  it("returns a probe failure while preserving the saved provider id", async () => {
    const deps = operations({
      testProvider: vi.fn().mockResolvedValue({
        provider_id: provider.id,
        success: false,
        model: model.model_id,
        error: "model unavailable",
      }),
    })
    const { result } = renderHook(() => useProviderConnection(deps))

    let outcome
    await act(async () => {
      outcome = await result.current.connect({ templateId: "openai" })
    })

    expect(outcome).toMatchObject({
      ok: false,
      stage: "probe",
      providerId: provider.id,
      error: expect.objectContaining({ message: "model unavailable" }),
    })
    expect(deps.activation.setSelectedModel).not.toHaveBeenCalled()
  })

  it("uses models returned by setup without redundant discovery", async () => {
    const deps = operations({
      setupProvider: vi.fn().mockResolvedValue({
        ok: true,
        result: { provider, models: [model], discovered: true },
      }),
    })
    const { result } = renderHook(() => useProviderConnection(deps))

    await act(async () => {
      await result.current.connect({ templateId: "openai" })
    })

    expect(deps.discoverModels).not.toHaveBeenCalled()
    expect(deps.activation.setSelectedModel).toHaveBeenCalledWith({
      provider: provider.id,
      model: model.model_id,
      model_id: model.id,
    })
  })

  it("selects the first setup model that supports tools", async () => {
    const textOnlyModel = {
      ...model,
      id: "model-text-only",
      model_id: "gpt-text-only",
      display_name: "GPT Text Only",
      supports_tools: undefined,
    }
    const deps = operations({
      setupProvider: vi.fn().mockResolvedValue({
        ok: true,
        result: {
          provider,
          models: [textOnlyModel, model],
          discovered: false,
        },
      }),
    })
    const { result } = renderHook(() => useProviderConnection(deps))

    let outcome
    await act(async () => {
      outcome = await result.current.connect({ templateId: "openai" })
    })

    expect(deps.testProvider).toHaveBeenCalledWith(provider.id, model.id)
    expect(deps.activation.setSelectedModel).toHaveBeenCalledWith({
      provider: provider.id,
      model: model.model_id,
      model_id: model.id,
    })
    expect(outcome).toMatchObject({ ok: true, modelId: model.id })
  })

  it("returns a model failure when setup models do not support tools", async () => {
    const deps = operations({
      setupProvider: vi.fn().mockResolvedValue({
        ok: true,
        result: {
          provider,
          models: [
            { ...model, supports_tools: false },
            {
              ...model,
              id: "model-unknown-tools",
              model_id: "gpt-unknown-tools",
              supports_tools: undefined,
            },
          ],
          discovered: false,
        },
      }),
    })
    const { result } = renderHook(() => useProviderConnection(deps))

    let outcome
    await act(async () => {
      outcome = await result.current.connect({ templateId: "openai" })
    })

    expect(outcome).toMatchObject({
      ok: false,
      stage: "model",
      providerId: provider.id,
    })
    expect(deps.testProvider).not.toHaveBeenCalled()
    expect(deps.activation.setSelectedModel).not.toHaveBeenCalled()
    expect(deps.activation.refreshSettings).not.toHaveBeenCalled()
  })

  it("preserves the active runtime selection when activation is disabled", async () => {
    const deps = operations({ activation: { mode: "preserve" as const } })
    const { result } = renderHook(() => useProviderConnection(deps))

    let outcome
    await act(async () => {
      outcome = await result.current.connect({ templateId: "openai" })
    })

    expect(outcome).toMatchObject({ ok: true, providerId: provider.id })
    expect(deps.testProvider).toHaveBeenCalledWith(provider.id, model.id)
  })
})
