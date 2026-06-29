import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { SystemStatus } from "@/app/(app)/dashboard/components/system-status"
import type { GpuInfo, ReadinessCheck, SystemHealth } from "@/app/(app)/dashboard/components/dashboard-types"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, string | number>) => {
    const copy: Record<string, string> = {
      systemStatus: "System Status",
      healthy: "Healthy",
      unavailable: "Unavailable",
      dockerAvailable: "Docker Status",
      gpuStatus: "GPU Status",
      "docker.badgePrefix": "Docker:",
      "docker.nvidiaRuntimePrefix": "NVIDIA Runtime:",
      "docker.available": "Available",
      "docker.notRunning": "Not running",
      "docker.notFound": "Not found",
      parabricksCompatible: "Parabricks Compatible",
      noGpuDetected: "No GPU detected",
      "gpu.nvidiaRuntimeVisible": "NVIDIA runtime visible",
      "gpu.detailsUnavailable": "GPU details unavailable to backend",
      "systemNotes.title": "Optional notes",
      "systemNotes.badge": "Doesn't block setup",
      "systemNotes.description": "These notes do not block CPU or local workflows.",
      "systemNotes.gpuRuntimeHiddenWithRecommendation": `This host supports GPU work, but containers cannot use the GPU yet. CPU and local workflows can run now. ${values?.recommendation ?? ""}`,
      "readiness.checks.gpu.label": "GPU",
    }

    return copy[key] ?? key
  },
}))

const healthyWithNvidiaRuntime: SystemHealth = {
  status: "healthy",
  docker: {
    available: true,
    nvidia_runtime: true,
  },
  gpu: {
    available: false,
    parabricks_compatible: false,
  },
  parabricks: {
    image_available: false,
    image_name: null,
  },
}

const runtimeOnlyGpu: GpuInfo = {
  available: false,
  nvidia_smi_found: false,
  docker_nvidia_runtime: true,
  parabricks_compatible: false,
  recommendation: "NVIDIA container runtime is configured, but nvidia-smi is not available to the backend process.",
  error: "nvidia-smi not found",
  gpus: [],
}

const gpuOptionalNote: ReadinessCheck = {
  id: "gpu",
  status: "warn",
  severity: "optional",
  facts: {
    docker_nvidia_runtime: true,
    runtime_visible_to_backend: false,
    recommendation: "Enable the GPU compose override only when a workflow needs acceleration.",
  },
}

describe("SystemStatus", () => {
  it("does not report no GPU when the NVIDIA runtime is visible", () => {
    render(<SystemStatus health={healthyWithNvidiaRuntime} gpuInfo={runtimeOnlyGpu} />)

    expect(screen.queryByText("No GPU detected")).not.toBeInTheDocument()
    expect(screen.getByText("NVIDIA runtime visible")).toBeInTheDocument()
    expect(screen.getByText(runtimeOnlyGpu.recommendation)).toBeInTheDocument()
  })

  it("shows optional readiness notes as non-blocking system guidance", () => {
    render(
      <SystemStatus
        health={healthyWithNvidiaRuntime}
        gpuInfo={runtimeOnlyGpu}
        optionalNotes={[gpuOptionalNote]}
      />,
    )

    expect(screen.getByText("Optional notes")).toBeInTheDocument()
    expect(screen.getByText("Doesn't block setup")).toBeInTheDocument()
    expect(screen.getByText("GPU")).toBeInTheDocument()
    expect(screen.getByText(/CPU and local workflows can run now/)).toBeInTheDocument()
  })
})
