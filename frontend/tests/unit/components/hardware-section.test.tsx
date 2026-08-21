import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const fetchMock = vi.fn()
const requestAdapterMock = vi.fn()
const originalGpu = Object.getOwnPropertyDescriptor(navigator, "gpu")

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const copy: Record<string, string> = {
      "gpu.title": "GPU",
      "gpu.spec": "RTX 4090",
      "gpu.description": "NVIDIA GPU with 16GB+ VRAM",
      "ram.title": "Memory",
      "ram.spec": "64GB+",
      "ram.description": "System RAM for genome data",
      "storage.title": "Storage",
      "storage.spec": "500GB+ SSD",
      "storage.description": "Fast storage for temp files",
      badge: "Local check",
      title: "Can this computer run WGS?",
      subtitle: "Check local hardware requirements.",
      checkButton: "Check your hardware",
      checking: "Checking...",
      detected: "Detected GPU",
      "diagnostic.title": "Local configuration",
      "diagnostic.status": "Not checked",
      "diagnostic.note": "Only local hardware details are read.",
      "status.ready": "Meets WGS requirements",
      "status.partial": "May work with limitations",
      "status.notCompatible": "NVIDIA GPU required",
      "status.noGpu": "No GPU detected",
      "status.cannotDetect": "Check your NVIDIA GPU manually",
      "status.unknownGpu": "Unknown GPU",
    }

    return copy[key] ?? key
  },
}))

import { HardwareSection } from "@/components/landing/hardware-section"

describe("HardwareSection", () => {
  beforeEach(() => {
    fetchMock.mockReset()
    requestAdapterMock.mockReset()
    vi.stubGlobal("fetch", fetchMock)
    Object.defineProperty(navigator, "gpu", {
      configurable: true,
      value: { requestAdapter: requestAdapterMock },
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    if (originalGpu) {
      Object.defineProperty(navigator, "gpu", originalGpu)
    } else {
      Reflect.deleteProperty(navigator, "gpu")
    }
  })

  it("reads a successful GPU response from its API envelope", async () => {
    const user = userEvent.setup()
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        data: {
          nvidia_smi_found: true,
          parabricks_compatible: true,
          recommendation: "Meets WGS requirements",
          gpus: [{ name: "NVIDIA RTX 4090" }],
        },
      }),
    })

    render(<HardwareSection />)

    const button = screen.getByRole("button", { name: "Check your hardware" })
    const status = screen.getByRole("status")
    expect(button).toHaveAttribute("aria-describedby", "hardware-diagnostic-status")
    expect(status).toHaveAttribute("id", "hardware-diagnostic-status")
    expect(status).toHaveAttribute("aria-live", "polite")
    expect(status).toHaveAttribute("aria-atomic", "true")

    await user.click(button)

    expect(await screen.findByText("Meets WGS requirements")).toBeInTheDocument()
    expect(screen.getByText("NVIDIA RTX 4090")).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/system/gpu")
    expect(requestAdapterMock).not.toHaveBeenCalled()
  })
})
