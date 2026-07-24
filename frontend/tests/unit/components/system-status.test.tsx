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
      "gpu.ready": "Ready for GPU workflows",
      "gpu.policyManual": "Manual · using 1 of 2 GPUs",
      "gpu.selected": "Selected",
      "gpu.selectedDeviceIds": "Selected device IDs",
      "gpu.moreDevices": "+7 more",
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

const manualH20Gpu = {
  available: true,
  detected: true,
  mode: "manual",
  state: "ready",
  detected_count: 2,
  selected_count: 1,
  selected_gpu_uuids: ["GPU-b"],
  container_toolkit_available: true,
  usable_for_gpu_workflows: true,
  nvidia_smi_found: true,
  docker_nvidia_runtime: true,
  parabricks_compatible: true,
  recommendation: "Manual GPU policy selected 1 of 2 detected GPUs.",
  error: null,
  gpus: [
    { index: 0, uuid: "GPU-a", name: "NVIDIA H20", selected: false, memory_total_mb: 97871, memory_free_mb: 96000, gpu_type: "NVIDIA" },
    { index: 1, uuid: "GPU-b", name: "NVIDIA H20", selected: true, memory_total_mb: 97871, memory_free_mb: 95000, gpu_type: "NVIDIA" },
  ],
} satisfies GpuInfo

const appleSiliconGpu = {
  available: true,
  detected: true,
  mode: "auto",
  state: "ready",
  detected_count: 1,
  selected_count: 0,
  selected_gpu_uuids: [],
  usable_for_gpu_workflows: false,
  parabricks_compatible: false,
  gpus: [
    { index: 0, name: "Apple M3 Max", selected: false, memory_total_mb: 49152, memory_free_mb: 0, gpu_type: "Apple Silicon" },
  ],
} satisfies GpuInfo

describe("SystemStatus", () => {
  it("does not report no GPU when the NVIDIA runtime is visible", () => {
    render(<SystemStatus health={healthyWithNvidiaRuntime} gpuInfo={runtimeOnlyGpu} />)

    expect(screen.queryByText("No GPU detected")).not.toBeInTheDocument()
    expect(screen.getByText("NVIDIA runtime visible")).toBeInTheDocument()
    expect(screen.queryByText("GPU details unavailable to backend")).not.toBeInTheDocument()
    expect(screen.queryByText(runtimeOnlyGpu.recommendation)).not.toBeInTheDocument()
  })

  it("shows detected H20 hardware separately from the selected GPU pool", () => {
    render(<SystemStatus health={healthyWithNvidiaRuntime} gpuInfo={manualH20Gpu} />)

    expect(screen.getByText("2 × NVIDIA H20")).toBeInTheDocument()
    expect(screen.getByText("Ready for GPU workflows")).toBeInTheDocument()
    expect(screen.getByText("Manual · using 1 of 2 GPUs")).toBeInTheDocument()
    expect(screen.getByText(/GPU-b/)).toBeInTheDocument()
  })

  it("keeps multi-GPU device identifiers compact", () => {
    const selectedGpuUuids = Array.from({ length: 8 }, (_, index) => `GPU-device-${index + 1}`)
    const manyH20Gpus = {
      ...manualH20Gpu,
      detected_count: 8,
      selected_count: 8,
      selected_gpu_uuids: selectedGpuUuids,
      gpus: selectedGpuUuids.map((uuid, index) => ({
        index,
        uuid,
        name: "NVIDIA H20",
        selected: true,
        memory_total_mb: 97871,
        memory_free_mb: 95000,
        gpu_type: "NVIDIA" as const,
      })),
    } satisfies GpuInfo

    render(<SystemStatus health={healthyWithNvidiaRuntime} gpuInfo={manyH20Gpus} />)

    expect(screen.getByText("Selected device IDs")).toBeInTheDocument()
    expect(screen.getByText("GPU-device-1")).toBeInTheDocument()
    expect(screen.getByText("+7 more")).toBeInTheDocument()
    expect(screen.queryByText("GPU-device-8")).not.toBeInTheDocument()
  })

  it("shows Apple Silicon as local hardware without claiming NVIDIA workflow readiness", () => {
    render(<SystemStatus health={healthyWithNvidiaRuntime} gpuInfo={appleSiliconGpu} />)

    expect(screen.getByText("Apple M3 Max")).toBeInTheDocument()
    expect(screen.queryByText("Ready for GPU workflows")).not.toBeInTheDocument()
    expect(screen.queryByText(/Automatic ·/)).not.toBeInTheDocument()
  })
})
