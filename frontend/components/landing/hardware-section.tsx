"use client";

import {
  Cpu,
  MemoryStick,
  HardDrive,
  CheckCircle2,
  AlertCircle,
} from "@/lib/icons";
import { Button } from "@/components/ui/button";
import {
  FadeInOnScroll,
  StaggerContainer,
  StaggerItem,
} from "@/components/ui/scroll-animations";
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
    <section id="hardware" className="section-padding">
      <div className="container mx-auto px-6">
        <FadeInOnScroll>
          <div className="text-center mb-14">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-gradient-to-r from-green-500/10 to-emerald-500/10 border border-green-500/20 text-green-600 dark:text-green-400 text-xs font-medium mb-4">
              <Cpu className="w-3 h-3" />
              {t("badge")}
            </span>
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-semibold tracking-tight mb-4">
              {t("title")}
            </h2>
            <p className="text-muted-foreground text-lg md:text-xl max-w-2xl mx-auto">
              {t("subtitle")}
            </p>
          </div>
        </FadeInOnScroll>

        <StaggerContainer
          className="grid md:grid-cols-3 gap-6 max-w-4xl mx-auto mb-12"
          staggerDelay={0.1}
        >
          {requirements.map((req) => (
            <StaggerItem key={req.id}>
              <div className="bg-card border border-border rounded-xl p-6 text-center hover:border-foreground/20 transition-colors duration-200">
                <div className="w-12 h-12 rounded-lg bg-secondary flex items-center justify-center mx-auto mb-4">
                  <req.icon className="w-6 h-6" />
                </div>
                <h3 className="text-lg font-semibold mb-1">{req.title}</h3>
                <p className="text-xl font-mono text-foreground mb-2">
                  {req.spec}
                </p>
                <p className="text-muted-foreground text-sm">
                  {req.description}
                </p>
              </div>
            </StaggerItem>
          ))}
        </StaggerContainer>

        <FadeInOnScroll delay={0.3}>
          <div className="flex flex-col items-center gap-4">
            <Button
              size="lg"
              variant={
                status.checked
                  ? status.compatible
                    ? "default"
                    : "outline"
                  : "default"
              }
              className="rounded-full px-8 gap-2"
              onClick={handleCheckHardware}
              disabled={checking}
            >
              {checking ? (
                <>
                  <span className="animate-spin">⏳</span>
                  {t("checking")}
                </>
              ) : status.checked ? (
                <>
                  {status.compatible ? (
                    <CheckCircle2 className="w-4 h-4 text-green-500" />
                  ) : (
                    <AlertCircle className="w-4 h-4" />
                  )}
                  {status.message}
                </>
              ) : (
                <>
                  <Cpu className="w-4 h-4" />
                  {t("checkButton")}
                </>
              )}
            </Button>

            {status.checked && status.gpu && (
              <p className="text-sm text-muted-foreground">
                {t("detected")}: <span className="font-mono">{status.gpu}</span>
              </p>
            )}
          </div>
        </FadeInOnScroll>
      </div>
    </section>
  );
}
