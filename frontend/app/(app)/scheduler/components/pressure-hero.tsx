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
    number: "text-success",
    pill: "bg-success-muted border-success-border text-success",
  },
  moderate: {
    number: "text-warning",
    pill: "bg-warning-muted border-warning-border text-warning",
  },
  saturated: {
    number: "text-destructive",
    pill: "bg-destructive-muted border-destructive-border text-destructive",
  },
}

/**
 * Deliberately designed to answer one question at a glance: *should I worry?*
 *
 * The large number is the composite. The 10-cell meter visualises the same
 * score with a spatial signal so the severity is legible even in peripheral
 * vision. The factors grid below lists the inputs that fed the score so the
 * operator can answer the follow-up *why?* without leaving the panel.
 */
export function PressureHero({ pressure, factors }: PressureHeroProps) {
  const t = useTranslations("scheduler")
  const styles = STATUS_STYLES[pressure.status]
  const lit = Math.round(pressure.score / 10)

  return (
    <div className="flex flex-col gap-4">
      <div className="font-mono text-[11px] uppercase tracking-[0.08em] text-muted-foreground">
        {t("pressure.label")}
      </div>
      <div className="flex items-baseline gap-3">
        <span
          className={`font-mono text-4xl font-medium tracking-tight transition-colors ${styles.number}`}
        >
          {pressure.score}%
        </span>
        <span
          className={`rounded-full border px-2.5 py-0.5 text-[11px] font-medium uppercase tracking-[0.08em] transition-colors ${styles.pill}`}
        >
          {t(`pressure.${pressure.status}`)}
        </span>
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
              className={`h-1 flex-1 rounded-sm transition-colors ${tone}`}
              aria-hidden="true"
            />
          )
        })}
      </div>
      <div className="grid grid-cols-2 gap-x-5 gap-y-1 text-[12px] text-muted-foreground">
        <FactorRow
          label={t("pressure.factors.cpu")}
          value={factors.cpu == null ? "—" : `${factors.cpu.toFixed(0)}%`}
        />
        <FactorRow
          label={t("pressure.factors.mem")}
          value={
            factors.memUsedGb == null
              ? "—"
              : `${factors.memUsedGb.toFixed(1)} GB`
          }
        />
        <FactorRow
          label={t("pressure.factors.load")}
          value={factors.load == null ? "—" : factors.load.toFixed(2)}
        />
        <FactorRow
          label={t("pressure.factors.queue")}
          value={String(factors.queueDepth)}
        />
      </div>
    </div>
  )
}

function FactorRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between border-b border-dashed border-divider pb-0.5 last:border-b-0">
      <span>{label}</span>
      <span className="font-mono font-medium text-foreground">{value}</span>
    </div>
  )
}
