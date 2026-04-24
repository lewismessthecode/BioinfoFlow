"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import {
  ArrowRight,
  Dna,
  FlaskConical,
  Sparkles,
  TestTube2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type TemplateData = {
  name: string;
  description: string;
};

interface WelcomeCardProps {
  onQuickCreate: (data: TemplateData) => Promise<void>;
  onOpenCreateDialog: () => void;
}

const TEMPLATE_ICONS = [Dna, FlaskConical, TestTube2] as const;
const TEMPLATE_ACCENTS = [
  {
    gradient:
      "linear-gradient(135deg, color-mix(in srgb, var(--primary) 10%, transparent), transparent 72%)",
    iconBackground:
      "color-mix(in srgb, var(--primary) 12%, transparent)",
    iconColor: "var(--primary)",
  },
  {
    gradient:
      "linear-gradient(135deg, color-mix(in srgb, var(--ring) 12%, transparent), transparent 72%)",
    iconBackground:
      "color-mix(in srgb, var(--ring) 12%, transparent)",
    iconColor: "var(--ring)",
  },
  {
    gradient:
      "linear-gradient(135deg, color-mix(in srgb, var(--accent) 92%, transparent), transparent 72%)",
    iconBackground:
      "color-mix(in srgb, var(--foreground) 8%, transparent)",
    iconColor: "var(--foreground)",
  },
] as const;

const TEMPLATE_KEYS = [
  { name: "blankName", description: "blankDescription" },
  { name: "wgsName", description: "wgsDescription" },
  { name: "rnaseqName", description: "rnaseqDescription" },
] as const;

export function WelcomeCard({
  onQuickCreate,
  onOpenCreateDialog,
}: WelcomeCardProps) {
  const t = useTranslations("welcome");
  const [isCreating, setIsCreating] = useState(false);

  const handleCreate = async (template: {
    name: string;
    description: string;
  }) => {
    setIsCreating(true);
    try {
      await onQuickCreate({
        name: t(template.name),
        description: t(template.description),
      });
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <section className="relative w-full overflow-hidden rounded-2xl border border-border/60 bg-background p-5 shadow-sm dark:bg-card md:p-6">
      <div className="pointer-events-none absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-foreground/10 to-transparent" />

      <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0 flex-1">
          <div className="inline-flex items-center gap-1.5 rounded-full bg-muted/60 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            <Sparkles className="h-3 w-3 text-primary" />
            {t("eyebrow")}
          </div>

          <h3 className="mt-3 text-xl font-semibold tracking-tight text-foreground md:text-2xl">
            {t("title")}
          </h3>
          <p className="mt-1.5 max-w-lg text-[13px] leading-6 text-muted-foreground">
            {t("subtitle")}
          </p>
        </div>

        <Button
          type="button"
          variant="outline"
          className="h-9 shrink-0 justify-between gap-6 rounded-xl border-border/80 px-3.5 text-[13px] text-foreground shadow-sm hover:bg-muted/45 md:self-end"
          onClick={onOpenCreateDialog}
        >
          <span>{t("customProject")}</span>
          <ArrowRight className="h-3.5 w-3.5" />
        </Button>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-3">
        {TEMPLATE_KEYS.map((template, index) => {
          const Icon = TEMPLATE_ICONS[index];
          const accent = TEMPLATE_ACCENTS[index];
          return (
            <button
              key={template.name}
              type="button"
              disabled={isCreating}
              onClick={() => handleCreate(template)}
                className={cn(
                "group flex items-center gap-3 rounded-xl border border-border/60 p-3 text-left transition-all duration-150 hover:border-foreground/15 hover:shadow-sm disabled:opacity-60",
              )}
              style={{ backgroundImage: accent.gradient }}
            >
              <div
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
                style={{
                  backgroundColor: accent.iconBackground,
                  color: accent.iconColor,
                }}
              >
                <Icon className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground">
                  {t(template.name)}
                </p>
                <p className="mt-0.5 text-xs leading-4 text-muted-foreground">
                  {t(template.description)}
                </p>
              </div>
              <ArrowRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60 transition-transform duration-150 group-hover:translate-x-0.5 group-hover:text-foreground/60" />
            </button>
          );
        })}
      </div>
    </section>
  );
}
