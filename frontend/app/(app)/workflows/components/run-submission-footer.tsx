"use client"

import { ChevronLeft, Eye, Loader2, Play } from "@/lib/icons"
import { useTranslations } from "next-intl"
import { Button } from "@/components/ui/button"

interface RunSubmissionFooterProps {
  previewOpen: boolean
  summary: string[]
  validationMessage: string | null
  previewPayload: Record<string, unknown>
  isSubmitting: boolean
  canSubmit: boolean
  onBackToPicker: () => void
  onTogglePreview: () => void
  onSubmit: () => void
}

export function RunSubmissionFooter({
  previewOpen,
  summary,
  validationMessage,
  previewPayload,
  isSubmitting,
  canSubmit,
  onBackToPicker,
  onTogglePreview,
  onSubmit,
}: RunSubmissionFooterProps) {
  const t = useTranslations("workflows.submission")

  return (
    <footer className="shrink-0 border-t border-border/60 bg-background/95 px-4 py-4 backdrop-blur sm:px-6">
      {previewOpen && (
        <div className="mb-4 overflow-hidden rounded-2xl border border-border/60 bg-muted/15">
          <div className="border-b border-border/60 px-4 py-2 text-sm font-medium text-foreground">
            {t("workbench.submissionPreview")}
          </div>
          <pre className="max-h-56 overflow-auto px-4 py-3 text-xs leading-5 text-muted-foreground">
            {JSON.stringify(previewPayload, null, 2)}
          </pre>
        </div>
      )}

      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2 text-sm text-foreground">
            {summary.map((item) => (
              <span
                key={item}
                className="rounded-full border border-border/60 bg-muted/15 px-3 py-1 text-xs"
              >
                {item}
              </span>
            ))}
          </div>
          {validationMessage && (
            <p className="text-xs text-destructive">{validationMessage}</p>
          )}
        </div>

        <div className="flex flex-col gap-2 sm:flex-row">
          <Button
            type="button"
            variant="outline"
            className="rounded-xl"
            onClick={onBackToPicker}
          >
            <ChevronLeft className="mr-2 h-4 w-4" />
            {t("workbench.changeWorkflow")}
          </Button>
          <Button
            type="button"
            variant="outline"
            className="rounded-xl"
            onClick={onTogglePreview}
          >
            <Eye className="mr-2 h-4 w-4" />
            {previewOpen ? t("workbench.hidePreview") : t("preview")}
          </Button>
          <Button
            type="button"
            className="rounded-xl"
            onClick={onSubmit}
            disabled={!canSubmit || isSubmitting}
          >
            {isSubmitting ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Play className="mr-2 h-4 w-4" />
            )}
            {isSubmitting ? t("submitting") : t("submitRun")}
          </Button>
        </div>
      </div>
    </footer>
  )
}
