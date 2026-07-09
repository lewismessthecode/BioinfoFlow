"use client";

import {
  Sparkles,
  HardDrive,
  FileJson,
  Activity,
  ChevronRight,
  Folder,
  Lock,
  Cpu,
  BarChart3,
} from "@/lib/icons";
import {
  FadeInOnScroll,
  StaggerContainer,
  StaggerItem,
} from "@/components/ui/scroll-animations";
import { useTranslations } from "next-intl";

function NodeVisual() {
  return (
    <div className="flex items-center justify-center gap-2">
      <div className="w-8 h-8 rounded-md bg-secondary border border-border flex items-center justify-center">
        <Sparkles className="w-3.5 h-3.5 text-muted-foreground" />
      </div>
      <ChevronRight className="w-3.5 h-3.5 text-muted-foreground/50" />
      <div className="space-y-1">
        <div className="w-10 h-4 rounded bg-secondary border border-border" />
        <div className="w-10 h-4 rounded bg-secondary border border-border" />
      </div>
      <ChevronRight className="w-3.5 h-3.5 text-muted-foreground/50" />
      <div className="w-8 h-8 rounded-md bg-foreground flex items-center justify-center">
        <Activity className="w-3.5 h-3.5 text-background" />
      </div>
    </div>
  );
}

function FolderVisual() {
  return (
    <div className="flex items-center justify-center gap-3">
      <div className="relative">
        <Folder className="w-8 h-8 text-muted-foreground/40" />
        <Lock className="w-3.5 h-3.5 absolute -bottom-0.5 -right-0.5 text-foreground" />
      </div>
      <div className="flex items-center gap-1.5">
        <div className="w-px h-6 bg-border" />
        <Cpu className="w-4 h-4 text-muted-foreground" />
      </div>
    </div>
  );
}

function ArtifactsVisual() {
  return (
    <div className="flex items-center justify-center gap-2">
      <div className="flex flex-col gap-0.5">
        <div className="w-10 h-1.5 rounded bg-muted-foreground/30" />
        <div className="w-8 h-1.5 rounded bg-muted-foreground/20" />
        <div className="w-6 h-1.5 rounded bg-muted-foreground/10" />
      </div>
      <FileJson className="w-4 h-4 text-muted-foreground" />
    </div>
  );
}

function ObservabilityVisual() {
  return (
    <div className="flex items-center justify-center gap-2">
      <div className="flex items-end gap-0.5 h-5">
        <div className="w-1 h-1.5 rounded-sm bg-muted-foreground/30" />
        <div className="w-1 h-3 rounded-sm bg-muted-foreground/50" />
        <div className="w-1 h-5 rounded-sm bg-foreground" />
        <div className="w-1 h-2.5 rounded-sm bg-muted-foreground/40" />
      </div>
      <BarChart3 className="w-4 h-4 text-muted-foreground" />
    </div>
  );
}

function GpuVisual() {
  return (
    <div className="flex items-center justify-center gap-3">
      <div className="flex flex-col items-center">
        <span className="text-xs text-muted-foreground">CPU</span>
        <span className="text-sm font-mono text-muted-foreground line-through">
          30h
        </span>
      </div>
      <ChevronRight className="w-4 h-4 text-green-500" />
      <div className="flex flex-col items-center">
        <span className="text-xs text-green-600 dark:text-green-400 font-medium">
          GPU
        </span>
        <span className="text-sm font-mono text-green-600 dark:text-green-400 font-bold">
          &lt;2h
        </span>
      </div>
    </div>
  );
}

export function BentoGrid() {
  const t = useTranslations("landing.bento");

  const features = [
    // {
    //   id: "gpu",
    //   title: t("gpu.title"),
    //   description: t("gpu.description"),
    //   icon: Zap,
    //   visual: "gpu",
    //   highlight: true
    // },
    {
      id: "agentic",
      title: t("agentic.title"),
      description: t("agentic.description"),
      icon: Sparkles,
      visual: "nodes",
    },
    {
      id: "local",
      title: t("local.title"),
      description: t("local.description"),
      icon: HardDrive,
      visual: "folders",
    },
    {
      id: "artifacts",
      title: t("artifacts.title"),
      description: t("artifacts.description"),
      icon: FileJson,
      visual: "artifacts",
    },
    {
      id: "observability",
      title: t("observability.title"),
      description: t("observability.description"),
      icon: Activity,
      visual: "observability",
    },
  ];

  return (
    <section id="features" className="section-padding bg-secondary/30">
      <div className="container mx-auto px-6">
        <FadeInOnScroll>
          <div className="text-center mb-14">
            <h2 className="text-3xl md:text-4xl lg:text-5xl font-semibold tracking-tight mb-4">
              {t("title")}
            </h2>
            <p className="text-muted-foreground text-lg md:text-xl max-w-2xl mx-auto">
              {t("subtitle")}
            </p>
          </div>
        </FadeInOnScroll>

        <StaggerContainer
          className="grid md:grid-cols-2 gap-4 lg:gap-5 max-w-4xl mx-auto"
          staggerDelay={0.1}
        >
          {features.map((feature) => (
            <StaggerItem key={feature.id}>
              <div className="h-full bg-card border border-border rounded-xl p-6 hover:border-foreground/20 transition-colors duration-200 hover:shadow-md group flex flex-col min-h-[200px]">
                <div className="flex items-start mb-4">
                  <div className="w-10 h-10 rounded-lg bg-secondary flex items-center justify-center group-hover:bg-foreground group-hover:text-background transition-colors duration-200">
                    <feature.icon className="w-5 h-5" />
                  </div>
                </div>

                <h3 className="text-lg font-semibold mb-2">{feature.title}</h3>
                <p className="text-muted-foreground text-sm leading-relaxed flex-1">
                  {feature.description}
                </p>

                <div className="mt-4 pt-4 border-t border-border">
                  {feature.visual === "gpu" && <GpuVisual />}
                  {feature.visual === "nodes" && <NodeVisual />}
                  {feature.visual === "folders" && <FolderVisual />}
                  {feature.visual === "artifacts" && <ArtifactsVisual />}
                  {feature.visual === "observability" && (
                    <ObservabilityVisual />
                  )}
                </div>
              </div>
            </StaggerItem>
          ))}
        </StaggerContainer>
      </div>
    </section>
  );
}
