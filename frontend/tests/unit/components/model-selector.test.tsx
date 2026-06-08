import { render, screen } from "@testing-library/react"
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
  ProviderIcon: ({ provider }: { provider: string }) => (
    <span aria-hidden="true" data-provider={provider} />
  ),
}))

const models: ProviderModels[] = [
  {
    provider: "openai",
    label: "OpenAI",
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
        selectedModel={{ provider: "openai", model: "gpt-4o-mini" }}
        onSelectModel={vi.fn()}
      />,
    )

    expect(screen.getByRole("combobox", { name: "GPT-4o mini" })).toHaveAttribute(
      "aria-label",
      "GPT-4o mini",
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
  })
})
