"use client"

import { useCallback, useRef, useState } from "react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import type { AgentActionDecision, AgentAnswer } from "@/lib/agent-runtime"
import type { AgentDecisionHandler } from "./types"

type DecisionOptions = { answer?: AgentAnswer; note?: string }
type DecisionRequest = {
  decision: AgentActionDecision
  options?: DecisionOptions
}

export function useDecisionSubmission(
  actionId: string,
  onDecision?: AgentDecisionHandler,
) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inFlightRef = useRef<Promise<void> | null>(null)
  const lastRequestRef = useRef<DecisionRequest | null>(null)

  const submit = useCallback(
    (decision: AgentActionDecision, options?: DecisionOptions) => {
      if (!onDecision) return Promise.resolve()
      if (inFlightRef.current) return inFlightRef.current
      lastRequestRef.current = { decision, options }
      setBusy(true)
      setError(null)

      let request: Promise<void>
      try {
        request = Promise.resolve(
          options
            ? onDecision(actionId, decision, options)
            : onDecision(actionId, decision),
        )
      } catch (submissionError) {
        request = Promise.reject(submissionError)
      }
      const tracked = request
        .catch((submissionError) => {
          setError(
            submissionError instanceof Error
              ? submissionError.message
              : "Failed to submit decision",
          )
        })
        .finally(() => {
          inFlightRef.current = null
          setBusy(false)
        })
      inFlightRef.current = tracked
      return tracked
    },
    [actionId, onDecision],
  )

  const retry = useCallback(() => {
    const request = lastRequestRef.current
    if (!request) return Promise.resolve()
    return submit(request.decision, request.options)
  }, [submit])

  return { busy, error, submit, retry }
}

export function DecisionSubmissionFeedback({
  busy,
  error,
  onRetry,
}: {
  busy: boolean
  error: string | null
  onRetry: () => void
}) {
  const t = useTranslations("agentRuntime")
  if (busy) {
    return (
      <div className="mt-2 text-xs text-muted-foreground" role="status" aria-live="polite">
        {t("decision.submitting")}
      </div>
    )
  }
  if (!error) return null
  return (
    <div
      className="mt-2 flex items-center gap-2 rounded-md border border-destructive/20 bg-destructive/5 px-2 py-1.5 text-xs text-destructive"
      role="alert"
    >
      <span className="min-w-0 flex-1">{t("decision.failed", { error })}</span>
      <Button
        type="button"
        size="sm"
        variant="outline"
        className="h-7 shrink-0 rounded-md px-2 text-xs"
        onClick={onRetry}
        aria-label={t("decision.retry")}
      >
        {t("decision.retry")}
      </Button>
    </div>
  )
}
