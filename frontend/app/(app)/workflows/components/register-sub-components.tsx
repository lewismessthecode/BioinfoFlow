import { useTranslations } from "next-intl"
import { AlertCircle } from "@/lib/icons"
import { cn } from "@/lib/utils"
import type { WorkflowValidationError } from "@/lib/types"
import type { RegistrationStep } from "./register-form-hook"

export function RegistrationProgress({ step }: { step: RegistrationStep | null }) {
  const tWorkflows = useTranslations("workflows")
  if (!step) return null
  const steps: { key: RegistrationStep; label: string }[] = [
    { key: "reading", label: tWorkflows("registerDialog.progress.reading") },
    { key: "validating", label: tWorkflows("registerDialog.progress.validating") },
    { key: "parsing", label: tWorkflows("registerDialog.progress.parsing") },
    { key: "registering", label: tWorkflows("registerDialog.progress.registering") },
  ]
  const currentIdx = steps.findIndex((s) => s.key === step)
  return (
    <div className="flex items-center gap-2.5 py-2.5">
      {steps.map((s, i) => (
        <div key={s.key} className="flex items-center gap-1.5">
          <div
            className={cn(
              "h-1.5 w-1.5 rounded-full transition-colors duration-150",
              i < currentIdx
                ? "bg-success"
                : i === currentIdx
                  ? "animate-pulse bg-primary"
                  : "bg-muted-foreground/30",
            )}
          />
          <span
            className={cn(
              "text-xs transition-colors",
              i <= currentIdx ? "text-foreground" : "text-muted-foreground",
            )}
          >
            {s.label}
          </span>
        </div>
      ))}
    </div>
  )
}

export function ValidationErrorList({
  errors,
  onErrorClick,
}: {
  errors: WorkflowValidationError[]
  onErrorClick: (line: number) => void
}) {
  const tWorkflows = useTranslations("workflows")
  return (
    <div className="space-y-1.5">
      <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-destructive">
        {tWorkflows("registerDialog.preview.validationErrors")}
      </p>
      <div className="max-h-[200px] space-y-1 overflow-y-auto">
        {errors.map((err, i) => (
          <button
            key={i}
            type="button"
            onClick={() => err.line && onErrorClick(err.line)}
            className="flex w-full items-start gap-2 rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-left text-sm transition-colors hover:bg-destructive/10"
          >
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
            <div>
              {err.line && (
                <span className="mr-1.5 font-mono text-xs text-destructive">L{err.line}</span>
              )}
              <span className="text-destructive/90">{err.message}</span>
            </div>
          </button>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        {tWorkflows("registerDialog.preview.clickToLocate")}
      </p>
    </div>
  )
}
