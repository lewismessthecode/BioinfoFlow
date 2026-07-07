"use client"

import { useTranslations } from "next-intl"
import type { PressureResult } from "./scoring"

type PressureHeroProps = {
  pressure: PressureResult
  factors: {
    cpu: number | null
    memUsedGb: number | null
    load: number | null
    queueDepth: number
  }
}

const STATUS_STYLES: Record<
  PressureResult["status"],
  { number: string; pill: string }
> = {
  healthy: {
    number: "text-foreground",
    pill: "bg-muted border-border text-muted-foreground",
  },
  moderate: {
    number: "text-warning",
    pill: "bg-warning-muted border-warning-border text-warning",
  },
  saturated: {
    number: "text-error",
    pill: "bg-error-muted border-error-border text-error",
  },
}

export function PressureHero({ pressure, factors }: PressureHeroProps) {
  const t = useTranslations("scheduler")
  const styles = STATUS_STYLES[pressure.status]
  const lit = Math.round(pressure.score / 10)

  return (
    <div className="space-y-4">
      <div>
        <div className="text-sm font-medium text-muted-foreground">
          {t("pressure.label")}
        </div>
        <div className="mt-2 flex flex-wrap items-baseline gap-3">
          <span
            className={`font-mono text-3xl font-medium tracking-tight transition-colors ${styles.number}`}
          >
            {pressure.score}%
          </span>
          <span
            className={`rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors ${styles.pill}`}
          >
            {t(`pressure.${pressure.status}`)}
          </span>
        </div>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          {t(`pressure.messages.${pressure.status}`)}
        </p>
      </div>

      <div className="flex gap-[3px]">
        {Array.from({ length: 10 }).map((_, i) => {
          const on = i < lit
          let tone = "bg-muted"
          if (on) {
            if (i >= 8) tone = "bg-destructive"
            else if (i >= 6) tone = "bg-warning"
            else tone = "bg-success"
          }
          return (
            <span
              key={i}
              className={`h-1.5 flex-1 rounded-sm transition-colors ${tone}`}
              aria-hidden="true"
            />
          )
        })}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <FactorPill
          label={t("pressure.factors.cpu")}
          value={factors.cpu == null ? "—" : `${factors.cpu.toFixed(0)}%`}
        />
        <FactorPill
          label={t("pressure.factors.mem")}
          value={
            factors.memUsedGb == null
              ? "—"
              : `${factors.memUsedGb.toFixed(1)} GB`
          }
        />
        <FactorPill
          label={t("pressure.factors.load")}
          value={factors.load == null ? "—" : factors.load.toFixed(2)}
        />
        <FactorPill
          label={t("pressure.factors.queue")}
          value={String(factors.queueDepth)}
        />
      </div>
    </div>
  )
}

function FactorPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border/70 bg-muted/20 px-3 py-2">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 font-mono text-sm font-medium text-foreground">{value}</p>
    </div>
  )
}
