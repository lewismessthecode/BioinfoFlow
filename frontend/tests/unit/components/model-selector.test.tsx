import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ModelSelector } from "@/components/bioinfoflow/chat/model-selector"
import type { ProviderModels } from "@/hooks/use-llm-settings"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const labels: Record<string, string> = {
      noProviders: "No model available",
      configure: "Configure providers",
      searchModels: "Search models...",
    }
    return labels[key] ?? key
  },
}))

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

vi.mock("@/components/bioinfoflow/chat/provider-icons", () => ({
  ProviderIcon: ({
    provider,
    baseUrl,
  }: {
    provider: string
    baseUrl?: string | null
  }) => (
    <span
      aria-hidden="true"
      data-base-url={baseUrl ?? ""}
      data-provider={provider}
      data-testid="provider-icon"
    />
  ),
}))

vi.stubGlobal(
  "ResizeObserver",
  class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  },
)
Element.prototype.scrollIntoView = vi.fn()

const models: ProviderModels[] = [
  {
    provider: "provider-openai",
    provider_kind: "openai",
    label: "OpenAI",
    base_url: "https://api.openai.com/v1",
    models: [
      {
        id: "gpt-4o-mini",
        name: "GPT-4o mini",
        context_window: 128000,
      },
    ],
  },
]

describe("ModelSelector", () => {
  it("keeps an accessible name when the selected model label is visually hidden on mobile", () => {
    render(
      <ModelSelector
        models={models}
        selectedModel={{ provider: "provider-openai", model: "gpt-4o-mini" }}
        onSelectModel={vi.fn()}
      />,
    )

    expect(screen.getByRole("combobox", { name: "GPT-4o mini" })).toHaveAttribute(
      "aria-label",
      "GPT-4o mini",
    )
    expect(screen.getByTestId("provider-icon")).toHaveAttribute(
      "data-base-url",
      "https://api.openai.com/v1",
    )
  })

  it("keeps an accessible name for the no-provider settings trigger", () => {
    render(
      <ModelSelector
        models={[]}
        selectedModel={null}
        onSelectModel={vi.fn()}
      />,
    )

    expect(screen.getByRole("link", { name: "Configure providers" })).toHaveAttribute(
      "aria-label",
      "Configure providers",
    )
    expect(screen.getByRole("link", { name: "Configure providers" })).toHaveAttribute(
      "href",
      "/settings?section=providers",
    )
  })

  it("uses a borderless composer trigger variant while keeping the combobox name", () => {
    render(
      <ModelSelector
        models={models}
        selectedModel={{ provider: "provider-openai", model: "gpt-4o-mini" }}
        onSelectModel={vi.fn()}
        variant="composer"
      />,
    )

    expect(screen.getByRole("combobox", { name: "GPT-4o mini" })).toHaveAttribute(
      "data-variant",
      "composer",
    )
    expect(screen.getByRole("combobox", { name: "GPT-4o mini" })).toHaveClass(
      "min-h-7",
      "leading-4",
    )
    expect(screen.getByRole("combobox", { name: "GPT-4o mini" })).not.toHaveClass(
      "h-[26px]",
      "leading-none",
    )
  })

  it("uses endpoint identity for same-kind providers and kind identity for icons", () => {
    const sameKindModels: ProviderModels[] = [
      {
        provider: "provider-relay-a",
        provider_kind: "openai_compatible",
        label: "Relay A",
        base_url: "https://relay-a.example/v1",
        models: [
          {
            id: "shared-model",
            name: "Shared Model on A",
            context_window: 128000,
            model_id: "model-relay-a",
          },
        ],
      },
      {
        provider: "provider-relay-b",
        provider_kind: "openai_compatible",
        label: "Relay B",
        base_url: "https://relay-b.example/v1",
        models: [
          {
            id: "shared-model",
            name: "Shared Model on B",
            context_window: 128000,
            model_id: "model-relay-b",
          },
        ],
      },
    ]

    render(
      <ModelSelector
        models={sameKindModels}
        selectedModel={{
          provider: "provider-relay-b",
          model: "shared-model",
          model_id: "model-relay-b",
        }}
        onSelectModel={vi.fn()}
      />,
    )

    expect(
      screen.getByRole("combobox", { name: "Shared Model on B" }),
    ).toBeInTheDocument()
    expect(screen.getByTestId("provider-icon")).toHaveAttribute(
      "data-provider",
      "openai_compatible",
    )
    expect(screen.getByTestId("provider-icon")).toHaveAttribute(
      "data-base-url",
      "https://relay-b.example/v1",
    )
  })

  it("searches models by provider display name", () => {
    render(
      <ModelSelector
        models={[
          {
            provider: "7a4cc090-43d2-4c47-b26a-915721caeac0",
            provider_kind: "openai_compatible",
            label: "Research Relay",
            base_url: "https://relay.example/v1",
            models: [
              {
                id: "gpt-5.4-mini",
                name: "GPT-5.4 Mini",
                context_window: 128000,
                model_id: "model-relay",
              },
            ],
          },
        ]}
        selectedModel={null}
        onSelectModel={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole("combobox"))
    fireEvent.change(screen.getByPlaceholderText("Search models..."), {
      target: { value: "Research Relay" },
    })

    expect(screen.getByText("GPT-5.4 Mini")).toBeInTheDocument()
  })
})
