"use client"

import { useState } from "react"
import { ChevronDown } from "@/lib/icons"
import { useTranslations } from "next-intl"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { cn } from "@/lib/utils"
import type { RetryPolicy } from "@/lib/types"

export interface AdvancedOptionsState {
  retryPolicy: RetryPolicy | null
  timeoutSeconds: number | null
}

interface RunAdvancedOptionsProps {
  value: AdvancedOptionsState
  onChange: (value: AdvancedOptionsState) => void
}

const DEFAULT_RETRY: RetryPolicy = {
  max_retries: 3,
  delay_seconds: 10,
  backoff_multiplier: 2.0,
  max_delay_seconds: 300,
  retry_on: [],
}

export function RunAdvancedOptions({ value, onChange }: RunAdvancedOptionsProps) {
  const t = useTranslations("workflows.wizard.advanced")
  const [isOpen, setIsOpen] = useState(false)

  const retryEnabled = value.retryPolicy !== null
  const retry = value.retryPolicy ?? DEFAULT_RETRY

  const handleRetryToggle = () => {
    onChange({ ...value, retryPolicy: retryEnabled ? null : DEFAULT_RETRY })
  }

  const updateRetry = (patch: Partial<RetryPolicy>) => {
    onChange({ ...value, retryPolicy: { ...retry, ...patch } })
  }

  const handleTimeoutChange = (raw: string) => {
    const n = raw.trim() ? parseInt(raw, 10) : NaN
    onChange({ ...value, timeoutSeconds: Number.isNaN(n) || n <= 0 ? null : n })
  }

  return (
    <div>
      <button
        type="button"
        className="flex w-full items-center justify-between py-1 text-xs-tight font-medium text-muted-foreground hover:text-foreground transition-colors"
        onClick={() => setIsOpen((prev) => !prev)}
      >
        {t("title")}
        <ChevronDown className={cn("h-3 w-3 transition-transform", isOpen && "rotate-180")} />
      </button>

      <div className={cn("grid transition-[grid-template-rows] duration-200", isOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]")}>
        <div className="overflow-hidden">
          <div className="pt-2 space-y-2">
            {/* Timeout */}
            <div>
              <label className="text-2xs uppercase tracking-wider text-muted-foreground font-medium block mb-0.5">
                {t("timeoutLabel")}
              </label>
              <Input
                type="number"
                min={0}
                placeholder={t("timeoutPlaceholder")}
                value={value.timeoutSeconds ?? ""}
                onChange={(e) => handleTimeoutChange(e.target.value)}
                className="h-7 text-xs font-mono max-w-[160px]"
              />
            </div>

            {/* Retry toggle */}
            <div className="flex items-center gap-2 py-1">
              <Switch
                checked={retryEnabled}
                onCheckedChange={handleRetryToggle}
                className="scale-75 origin-left"
              />
              <span className="text-xs text-foreground cursor-pointer" onClick={handleRetryToggle}>
                {t("retryEnable")}
              </span>
            </div>

            {/* Retry fields */}
            {retryEnabled && (
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-2xs text-muted-foreground font-medium block mb-0.5">{t("maxRetries")}</label>
                  <Input type="number" min={0} max={10} value={retry.max_retries} onChange={(e) => updateRetry({ max_retries: Math.min(10, Math.max(0, parseInt(e.target.value, 10) || 0)) })} className="h-7 text-xs font-mono" />
                </div>
                <div>
                  <label className="text-2xs text-muted-foreground font-medium block mb-0.5">{t("delaySeconds")}</label>
                  <Input type="number" min={0} value={retry.delay_seconds} onChange={(e) => updateRetry({ delay_seconds: Math.max(0, parseInt(e.target.value, 10) || 0) })} className="h-7 text-xs font-mono" />
                </div>
                <div>
                  <label className="text-2xs text-muted-foreground font-medium block mb-0.5">{t("backoffMultiplier")}</label>
                  <Input type="number" min={1} step={0.5} value={retry.backoff_multiplier} onChange={(e) => updateRetry({ backoff_multiplier: Math.max(1, parseFloat(e.target.value) || 1) })} className="h-7 text-xs font-mono" />
                </div>
                <div>
                  <label className="text-2xs text-muted-foreground font-medium block mb-0.5">{t("maxDelaySeconds")}</label>
                  <Input type="number" min={0} value={retry.max_delay_seconds} onChange={(e) => updateRetry({ max_delay_seconds: Math.max(0, parseInt(e.target.value, 10) || 0) })} className="h-7 text-xs font-mono" />
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
