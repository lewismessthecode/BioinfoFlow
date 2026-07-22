"use client";

import {
  Cpu,
  MemoryStick,
  HardDrive,
  CheckCircle2,
  AlertCircle,
  Loader2,
} from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { useTranslations } from "next-intl";
import { useState } from "react";

interface HardwareStatus {
  checked: boolean;
  compatible: boolean | null;
  gpu: string | null;
  message: string | null;
}

type WebGPUAdapterInfo = {
  device?: string;
  description?: string;
};

type WebGPUAdapter = {
  requestAdapterInfo: () => Promise<WebGPUAdapterInfo>;
};

type WebGPU = {
  requestAdapter: () => Promise<WebGPUAdapter | null>;
};

export function HardwareSection() {
  const t = useTranslations("landing.hardware");
  const [status, setStatus] = useState<HardwareStatus>({
    checked: false,
    compatible: null,
    gpu: null,
    message: null,
  });
  const [checking, setChecking] = useState(false);

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
  ];

  const handleCheckHardware = async () => {
    setChecking(true);

    // First, try backend API for accurate GPU detection (works when running locally)
    try {
      const response = await fetch("/api/v1/system/gpu");
      if (response.ok) {
        const data = await response.json();
        if (data.nvidia_smi_found) {
          // Backend detected GPU - most accurate
          const gpus = data.gpus || [];
          const gpuName = gpus.length > 0 ? gpus[0].name : null;

          setStatus({
            checked: true,
            compatible: data.parabricks_compatible,
            gpu: gpuName,
            message: data.recommendation,
          });
          setChecking(false);
          return;
        }
      }
    } catch {
      // Backend not available, fall back to WebGPU
    }

    // Fallback: Try to detect GPU using WebGPU API (browser-side)
    try {
      if ("gpu" in navigator) {
        const adapter = await (
          navigator as Navigator & { gpu: WebGPU }
        ).gpu.requestAdapter();
        if (adapter) {
          const info = await adapter.requestAdapterInfo();
          const gpuName = info.device || info.description || "Unknown GPU";
          const isNvidia =
            gpuName.toLowerCase().includes("nvidia") ||
            gpuName.toLowerCase().includes("geforce") ||
            gpuName.toLowerCase().includes("rtx");
          const isHighEnd =
            gpuName.toLowerCase().includes("4080") ||
            gpuName.toLowerCase().includes("4090") ||
            gpuName.toLowerCase().includes("3090") ||
            gpuName.toLowerCase().includes("a100");

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
          });
        } else {
          setStatus({
            checked: true,
            compatible: false,
            gpu: null,
            message: t("status.noGpu"),
          });
        }
      } else {
        // WebGPU not available, show demo message
        setStatus({
          checked: true,
          compatible: null,
          gpu: null,
          message: t("status.cannotDetect"),
        });
      }
    } catch {
      setStatus({
        checked: true,
        compatible: null,
        gpu: null,
        message: t("status.cannotDetect"),
      });
    }

    setChecking(false);
  };

  return (
    <section id="hardware" className="landing-hardware border-y border-border px-5 py-28 md:px-8 md:py-40">
      <div className="mx-auto grid max-w-7xl gap-14 lg:grid-cols-[0.82fr_1.18fr] lg:gap-24">
        <div className="lg:self-center">
          <p className="mb-5 text-sm font-medium text-[var(--brand-accent)]">{t("badge")}</p>
          <h2 className="max-w-lg text-balance text-3xl font-medium tracking-[-0.035em] md:text-5xl">
            {t("title")}
          </h2>
          <p className="mt-5 max-w-lg text-base leading-7 text-muted-foreground">
            {t("subtitle")}
          </p>
          <div className="mt-9 flex flex-col items-start gap-4">
            <Button
              size="lg"
              variant={
                status.checked
                  ? status.compatible
                    ? "default"
                    : "outline"
                  : "default"
              }
              className="gap-2 rounded-md px-5 shadow-none active:translate-y-px"
              onClick={handleCheckHardware}
              disabled={checking}
            >
              {checking ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  {t("checking")}
                </>
              ) : status.checked ? (
                <>
                  {status.compatible ? (
                    <CheckCircle2 className="size-4 text-success" />
                  ) : (
                    <AlertCircle className="size-4" />
                  )}
                  {status.message}
                </>
              ) : (
                <>
                  <Cpu className="size-4" />
                  {t("checkButton")}
                </>
              )}
            </Button>

            {status.checked && status.gpu && (
              <p className="text-sm text-muted-foreground" aria-live="polite">
                {t("detected")}: <span className="font-mono">{status.gpu}</span>
              </p>
            )}
          </div>
        </div>

        <div className="landing-evidence-panel overflow-hidden rounded-xl border border-border bg-background shadow-[var(--landing-shadow-soft)]">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <div className="flex items-center gap-3">
              <span className="relative flex size-2.5">
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-[var(--brand-accent)] opacity-30 motion-reduce:animate-none" />
                <span className="relative inline-flex size-2.5 rounded-full bg-[var(--brand-accent)]" />
              </span>
              <span className="text-sm font-medium">{t("diagnostic.title")}</span>
            </div>
            <span className="font-mono text-[0.65rem] uppercase tracking-[0.14em] text-muted-foreground">
              {t("diagnostic.status")}
            </span>
          </div>

          <div className="grid md:grid-cols-2">
            {requirements.map((req, index) => (
              <article
                key={req.id}
                className="group min-h-56 border-b border-border p-6 md:p-8 md:odd:border-r md:last:col-span-2 md:last:border-b-0"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex size-11 items-center justify-center rounded-md border border-border bg-secondary/45">
                    <req.icon className="size-5 text-muted-foreground" />
                  </div>
                  <span className="font-mono text-[0.65rem] text-muted-foreground">0{index + 1}</span>
                </div>
                <p className="mt-9 font-mono text-2xl tracking-[-0.04em]">{req.spec}</p>
                <h3 className="mt-4 font-medium">{req.title}</h3>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{req.description}</p>
              </article>
            ))}
          </div>

          <div className="flex flex-col gap-2 border-t border-border bg-secondary/30 px-5 py-4 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
            <span>{t("diagnostic.note")}</span>
            <span className="font-mono text-foreground/70">Bioinfoflow / local check</span>
          </div>
        </div>
      </div>
    </section>
  );
}
