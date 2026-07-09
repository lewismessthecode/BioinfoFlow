"use client"

import { useState } from "react"
import { Database, Settings2, X } from "@/lib/icons"
import { useTranslations } from "next-intl"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import { RunAdvancedOptions, type AdvancedOptionsState } from "./run-advanced-options"

interface RunSharedSettingsProps {
  projectId: string
  profile: string
  onProfileChange: (value: string) => void
  advancedOptions: AdvancedOptionsState
  onAdvancedOptionsChange: (value: AdvancedOptionsState) => void
}

export function RunSharedSettings({
  profile,
  onProfileChange,
  advancedOptions,
  onAdvancedOptionsChange,
}: RunSharedSettingsProps) {
  const t = useTranslations("workflows.submission")
  const tStep2 = useTranslations("workflows.submission.step2")
  const [showAdvanced, setShowAdvanced] = useState(false)

  const hasAdvancedSettings =
    profile.trim().length > 0 ||
    advancedOptions.retryPolicy !== null ||
    advancedOptions.timeoutSeconds !== null

  const profileChip = profile.trim()
  const timeoutChip = advancedOptions.timeoutSeconds
  const retryChip = advancedOptions.retryPolicy?.max_retries

  return (
    <section className="shrink-0 border-b border-border/60 bg-muted/15 px-4 py-2 sm:px-6">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-border/60 bg-background/80 px-2.5 py-1 text-[11px] text-muted-foreground">
          <Database className="h-3 w-3" />
          {tStep2("managedStorageLabel") ?? "Managed Storage"}
        </span>

        {profileChip && (
          <Chip label={t("workbench.chipProfile", { value: profileChip })} onClear={() => onProfileChange("")} />
        )}
        {typeof timeoutChip === "number" && (
          <Chip
            label={t("workbench.chipTimeout", { value: timeoutChip })}
            onClear={() =>
              onAdvancedOptionsChange({ ...advancedOptions, timeoutSeconds: null })
            }
          />
        )}
        {typeof retryChip === "number" && (
          <Chip
            label={t("workbench.chipRetry", { count: retryChip })}
            onClear={() =>
              onAdvancedOptionsChange({ ...advancedOptions, retryPolicy: null })
            }
          />
        )}

        <Button
          type="button"
          variant="ghost"
          size="sm"
          className={cn(
            "ml-auto h-7 rounded-full border border-border/60 bg-background/80 px-2.5 text-[11px]",
            hasAdvancedSettings && "border-primary/30 text-foreground",
            showAdvanced && "bg-muted",
          )}
          onClick={() => setShowAdvanced((current) => !current)}
          aria-expanded={showAdvanced}
        >
          <Settings2 className="mr-1.5 h-3 w-3" />
          {tStep2("advancedSettings") ?? "Run Settings"}
          {hasAdvancedSettings && <span className="ml-1.5 h-1.5 w-1.5 rounded-full bg-primary" />}
        </Button>
      </div>

      {showAdvanced && (
        <div className="mt-2 rounded-xl border border-border/60 bg-background/70 p-3">
          <div className="grid gap-3 lg:grid-cols-[minmax(0,260px)_minmax(0,1fr)]">
            <div className="rounded-lg border border-border/50 bg-muted/20 px-3 py-2">
              <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                {tStep2("profileLabel") ?? "Profile"}
              </p>
              <Input
                value={profile}
                onChange={(event) => onProfileChange(event.target.value)}
                className="mt-1.5 h-8 font-mono text-xs"
                placeholder="docker"
              />
            </div>
            <RunAdvancedOptions
              value={advancedOptions}
              onChange={onAdvancedOptionsChange}
            />
          </div>
        </div>
      )}
    </section>
  )
}

function Chip({ label, onClear }: { label: string; onClear?: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-primary/30 bg-primary/5 px-2.5 py-1 text-[11px] text-foreground">
      {label}
      {onClear && (
        <button
          type="button"
          onClick={onClear}
          className="text-muted-foreground hover:text-foreground"
          aria-label="clear"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </span>
  )
}
