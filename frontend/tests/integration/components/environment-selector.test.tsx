import { screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { useState } from "react"
import { describe, expect, it, vi } from "vitest"

import {
  EnvironmentSelector,
  type AgentEnvironmentSelection,
  type AgentEnvironmentTarget,
} from "@/components/bioinfoflow/agent/environment-selector"
import { renderWithProviders } from "@/tests/test-utils"

vi.mock("next-intl", () => ({
  useTranslations:
    () =>
    (key: string, values?: Record<string, number | string>) => {
      const copy: Record<string, string> = {
        label: "Execution environments",
        title: "Choose visible environments",
        "auto.name": "Auto",
        "auto.summary": "All environments",
        "auto.description": "Let the agent use any available environment.",
        "manual.name": "Manual",
        "manual.description": "Limit the agent to selected environments.",
        local: "Local",
        targetCount: "{count} environments",
        updating: "Updating environments…",
        updateError: "Environments could not be updated.",
        retry: "Retry environment update",
        "status.online": "Online",
        "status.offline": "Offline",
        "status.error": "Error",
        "status.unknown": "Unknown",
      }
      return (copy[key] ?? key).replace(
        "{count}",
        String(values?.count ?? "{count}"),
      )
    },
}))

const targets: AgentEnvironmentTarget[] = [
  {
    id: "local",
    label: "Local",
    description: "/Users/lewisliu/BioinfoFlow",
    kind: "local",
    status: "online",
  },
  {
    id: "gpu-01",
    label: "GPU analysis cluster with a deliberately long display name",
    description: "researcher@10.227.5.224:22/very/long/working/directory",
    kind: "ssh",
    status: "offline",
  },
  {
    id: "archive",
    label: "Archive node",
    description: "bio@archive.internal:22",
    kind: "ssh",
  },
]

function StatefulSelector({
  initial = { mode: "auto" },
  onChange = vi.fn(),
}: {
  initial?: AgentEnvironmentSelection
  onChange?: (selection: AgentEnvironmentSelection) => void
}) {
  const [selection, setSelection] = useState(initial)
  return (
    <EnvironmentSelector
      targets={targets}
      requested={selection}
      effective={selection}
      onChange={async (nextSelection) => {
        onChange(nextSelection)
        setSelection(nextSelection)
      }}
    />
  )
}

describe("EnvironmentSelector", () => {
  it("keeps the shared composer control while summarizing scope instead of repeating Auto", () => {
    renderWithProviders(<StatefulSelector />)

    const trigger = screen.getByRole("button", {
      name: "Execution environments: Auto, All environments",
    })

    expect(trigger).toHaveAttribute("data-composer-selector-metrics", "shared")
    expect(trigger).toHaveTextContent(/^All environments$/)
    expect(trigger).not.toHaveTextContent(/^Auto$/)
  })

  it("keeps Auto and Manual behavior while supporting multiple selected targets", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    renderWithProviders(<StatefulSelector onChange={onChange} />)

    await user.click(
      screen.getByRole("button", {
        name: "Execution environments: Auto, All environments",
      }),
    )
    await user.click(screen.getByRole("menuitemradio", { name: /Manual/i }))

    expect(onChange).toHaveBeenCalledWith({
      mode: "manual",
      targetIds: ["local"],
    })

    await user.click(
      screen.getByRole("menuitemcheckbox", { name: /GPU analysis cluster/i }),
    )

    expect(onChange).toHaveBeenLastCalledWith({
      mode: "manual",
      targetIds: ["local", "gpu-01"],
    })
    await user.keyboard("{Escape}")
    expect(
      screen.getByRole("button", {
        name: "Execution environments: Manual, 2 environments",
      }),
    ).toHaveTextContent(/^2 environments$/)
  })

  it("uses a responsive two-column target row with truncated identity and compact status badges", async () => {
    const user = userEvent.setup()
    renderWithProviders(
      <StatefulSelector initial={{ mode: "manual", targetIds: ["local"] }} />,
    )

    await user.click(
      screen.getByRole("button", {
        name: "Execution environments: Manual, Local",
      }),
    )

    const menu = screen.getByTestId("composer-selector-menu")
    expect(menu).toHaveAttribute(
      "data-composer-selector-menu-density",
      "compact",
    )
    expect(menu).toHaveClass("max-w-[calc(100vw-1.5rem)]")

    const remoteItem = screen.getByRole("menuitemcheckbox", {
      name: /GPU analysis cluster.*Offline/i,
    })
    const remoteRow = remoteItem.querySelector("[data-environment-target-row]")
    expect(remoteRow).toHaveClass(
      "grid",
      "grid-cols-[minmax(0,1fr)_auto]",
    )
    expect(
      within(remoteItem).getByText(
        "GPU analysis cluster with a deliberately long display name",
      ),
    ).toHaveClass("truncate")
    expect(
      within(remoteItem).getByText(
        "researcher@10.227.5.224:22/very/long/working/directory",
      ),
    ).toHaveClass("truncate")

    const offlineBadge = within(remoteItem).getByText("Offline")
    expect(offlineBadge).toHaveAttribute("data-environment-status", "offline")
    expect(offlineBadge).toHaveClass(
      "shrink-0",
      "whitespace-nowrap",
      "rounded-full",
    )

    const unknownItem = screen.getByRole("menuitemcheckbox", {
      name: /Archive node.*Unknown/i,
    })
    const unknownBadge = within(unknownItem).getByText("Unknown")
    expect(unknownBadge).toHaveAttribute("data-environment-status", "unknown")
    expect(unknownBadge).toHaveClass(
      "whitespace-nowrap",
      "dark:text-amber-300",
    )
  })
})
