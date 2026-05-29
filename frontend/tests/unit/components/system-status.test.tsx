import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { SystemStatus } from "@/app/(app)/dashboard/components/system-status"
import type { GpuInfo, SystemHealth } from "@/app/(app)/dashboard/components/dashboard-types"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
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

describe("SystemStatus", () => {
  it("does not report no GPU when the NVIDIA runtime is visible", () => {
    render(<SystemStatus health={healthyWithNvidiaRuntime} gpuInfo={runtimeOnlyGpu} />)

    expect(screen.queryByText("No GPU detected")).not.toBeInTheDocument()
    expect(screen.getByText("NVIDIA runtime visible")).toBeInTheDocument()
    expect(screen.getByText(runtimeOnlyGpu.recommendation)).toBeInTheDocument()
  })
})
