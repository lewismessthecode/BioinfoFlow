"use client"

import { useState } from "react"
import {
  AlertCircle,
  CheckCircle2,
  Cpu,
  HardDrive,
  Loader2,
  MemoryStick,
} from "@/lib/icons"
import { Button } from "@/components/ui/button"
import { useTranslations } from "next-intl"
import type { ApiEnvelope } from "@/lib/types"

interface HardwareStatus {
  checked: boolean
  compatible: boolean | null
  gpu: string | null
  message: string | null
}

type GpuStatusPayload = {
  nvidia_smi_found: boolean
  parabricks_compatible: boolean
  recommendation: string
  gpus: Array<{ name?: string | null }>
}

type WebGPUAdapterInfo = {
  device?: string
  description?: string
}

type WebGPUAdapter = {
  requestAdapterInfo: () => Promise<WebGPUAdapterInfo>
}

type WebGPU = {
  requestAdapter: () => Promise<WebGPUAdapter | null>
}

export function HardwareSection() {
  const t = useTranslations("landing.hardware")
  const [status, setStatus] = useState<HardwareStatus>({
    checked: false,
    compatible: null,
    gpu: null,
    message: null,
  })
  const [checking, setChecking] = useState(false)

  const requirements = [
    {
      id: "gpu",
      icon: Cpu,
      title: t("gpu.title"),
      spec: t("gpu.spec"),
      description: t("gpu.description"),
    },
    {
      id: "ram",
      icon: MemoryStick,
      title: t("ram.title"),
      spec: t("ram.spec"),
      description: t("ram.description"),
    },
    {
      id: "storage",
      icon: HardDrive,
      title: t("storage.title"),
      spec: t("storage.spec"),
      description: t("storage.description"),
    },
  ]

  const handleCheckHardware = async () => {
    setChecking(true)

    try {
      try {
        const response = await fetch("/api/v1/system/gpu")
        if (response.ok) {
          const payload = (await response.json()) as ApiEnvelope<GpuStatusPayload>
          if (payload.success && payload.data.nvidia_smi_found) {
            setStatus({
              checked: true,
              compatible: payload.data.parabricks_compatible,
              gpu: payload.data.gpus[0]?.name ?? null,
              message: payload.data.recommendation,
            })
            return
          }
        }
      } catch {
        // The browser-side fallback is useful for remote and preview deployments.
      }

      try {
        if ("gpu" in navigator) {
          const adapter = await (
            navigator as Navigator & { gpu: WebGPU }
          ).gpu.requestAdapter()
          if (adapter) {
            const info = await adapter.requestAdapterInfo()
            const gpuName = info.device || info.description || t("status.unknownGpu")
            const isNvidia =
              gpuName.toLowerCase().includes("nvidia") ||
              gpuName.toLowerCase().includes("geforce") ||
              gpuName.toLowerCase().includes("rtx")
            const isHighEnd =
              gpuName.toLowerCase().includes("4080") ||
              gpuName.toLowerCase().includes("4090") ||
              gpuName.toLowerCase().includes("3090") ||
              gpuName.toLowerCase().includes("a100")

            setStatus({
              checked: true,
              compatible: isNvidia && isHighEnd,
              gpu: gpuName,
              message:
                isNvidia && isHighEnd
                  ? t("status.ready")
                  : isNvidia
                    ? t("status.partial")
                    : t("status.notCompatible"),
            })
          } else {
            setStatus({
              checked: true,
              compatible: false,
              gpu: null,
              message: t("status.noGpu"),
            })
          }
        } else {
          setStatus({
            checked: true,
            compatible: null,
            gpu: null,
            message: t("status.cannotDetect"),
          })
        }
      } catch {
        setStatus({
          checked: true,
          compatible: null,
          gpu: null,
          message: t("status.cannotDetect"),
        })
      }
    } finally {
      setChecking(false)
    }
  }

  const statusMessage = status.message ?? t("diagnostic.status")

  return (
    <section id="hardware" className="landing-hardware border-y border-border px-5 py-28 md:px-8 md:py-40">
      <div className="landing-narrative-layout mx-auto grid max-w-7xl gap-14">
        <div className="xl:self-center">
          <p className="landing-section-kicker">{t("badge")}</p>
          <h2 className="mt-5 max-w-lg text-3xl font-medium tracking-[-0.04em] md:text-5xl">
            <span className="block">{t("titleLead")}</span>
            <span className="block">{t("titleRest")}</span>
          </h2>
          <p className="mt-5 max-w-lg text-base leading-7 text-muted-foreground">
            {t("subtitle")}
          </p>
          <div className="mt-9 flex flex-col items-start gap-4">
            <Button
              size="lg"
              variant={status.checked && !status.compatible ? "outline" : "default"}
              className="gap-2 rounded-md px-5 shadow-none active:translate-y-px"
              onClick={handleCheckHardware}
              disabled={checking}
              aria-describedby="hardware-diagnostic-status"
            >
              {checking ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  {t("checking")}
                </>
              ) : (
                <>
                  <Cpu className="size-4" />
                  {t("checkButton")}
                </>
              )}
            </Button>
          </div>
        </div>

        <div className="landing-evidence-surface overflow-hidden border border-border bg-background">
          <div className="landing-evidence-header">
            <div>
              <p className="text-sm font-medium">{t("diagnostic.title")}</p>
              <p className="mt-1 max-w-md text-sm leading-6 text-muted-foreground">
                {t("diagnostic.note")}
              </p>
            </div>
            <div
              id="hardware-diagnostic-status"
              className="landing-evidence-status"
              role="status"
              aria-live="polite"
              aria-atomic="true"
            >
              {status.checked ? (
                <>
                  <p className="inline-flex items-center gap-2 text-sm font-medium text-foreground">
                    {status.compatible ? (
                      <CheckCircle2 className="size-4 shrink-0 text-success" />
                    ) : (
                      <AlertCircle className="size-4 shrink-0 text-[var(--brand-accent)]" />
                    )}
                    {statusMessage}
                  </p>
                  {status.gpu && (
                    <p className="mt-1 break-words text-sm text-muted-foreground">
                      {t("detected")}:{" "}
                      <span className="font-mono text-foreground">{status.gpu}</span>
                    </p>
                  )}
                </>
              ) : (
                <p className="text-sm text-muted-foreground">{statusMessage}</p>
              )}
            </div>
          </div>

          <div className="landing-evidence-list">
            {requirements.map((requirement) => (
              <article
                key={requirement.id}
                className="landing-evidence-row group grid gap-4 border-b border-border p-6 last:border-b-0 sm:grid-cols-[2.75rem_minmax(0,1fr)_auto] sm:items-start sm:gap-5 sm:p-8"
              >
                <div className="landing-evidence-mark flex size-11 items-center justify-center border border-border bg-secondary/45">
                  <requirement.icon className="size-5 text-muted-foreground" />
                </div>
                <div className="min-w-0">
                  <h3 className="font-medium tracking-tight">{requirement.title}</h3>
                  <p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">
                    {requirement.description}
                  </p>
                </div>
                <p className="landing-evidence-spec font-mono text-lg tracking-[-0.04em] text-foreground sm:text-right">
                  {requirement.spec}
                </p>
              </article>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
