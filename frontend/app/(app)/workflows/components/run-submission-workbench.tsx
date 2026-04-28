"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useTranslations } from "next-intl"
import { toast } from "sonner"
import { apiRequest, getApiErrorMessage } from "@/lib/api"
import {
  buildInitialValues,
  countFilledFields,
  validateValues,
  type FormValues,
  type RunCreateV2,
} from "@/lib/form-spec"
import { useFormSpec } from "@/hooks/use-form-spec"
import type { Workflow } from "@/lib/types"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { RunSharedSettings } from "./run-shared-settings"
import { RunSubmissionFooter } from "./run-submission-footer"
import { RunSubmissionHeader } from "./run-submission-header"
import { RunInputFileImport } from "./run-input-file-import"
import { RunForm } from "./run-form/run-form"
import type { AdvancedOptionsState } from "./run-advanced-options"

interface RunSubmissionWorkbenchProps {
  workflow: Workflow
  projectId: string
  onClose: () => void
  onChangeWorkflow: () => void
  onSubmitted: (runId: string) => void
}

export function RunSubmissionWorkbench({
  workflow,
  projectId,
  onClose,
  onChangeWorkflow,
  onSubmitted,
}: RunSubmissionWorkbenchProps) {
  const t = useTranslations("workflows.submission")
  const tForm = useTranslations("workflows.runForm")
  const specState = useFormSpec(workflow.id)

  const [values, setValues] = useState<FormValues>({})
  const [profile, setProfile] = useState("")
  const [advancedOptions, setAdvancedOptions] = useState<AdvancedOptionsState>({
    retryPolicy: null,
    timeoutSeconds: null,
  })
  const [previewOpen, setPreviewOpen] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [activeTab, setActiveTab] = useState("form")

  // Seed defaults the first time a spec arrives for this workflow. Subsequent
  // user edits live in `values`; we re-seed only when the workflow changes.
  useEffect(() => {
    if (specState.status === "ready") {
      setValues(buildInitialValues(specState.spec))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- spec identity is what we care about
  }, [workflow.id, specState.status === "ready" ? specState.spec : null])

  const validation = useMemo(() => {
    if (specState.status !== "ready") return { ok: false, issues: [] }
    return validateValues(specState.spec, values)
  }, [specState, values])

  const previewPayload = useMemo<RunCreateV2>(
    () => ({
      project_id: projectId,
      workflow_id: workflow.id,
      values,
      options: {
        profile: profile.trim() || null,
        max_retries: advancedOptions.retryPolicy?.max_retries ?? null,
        timeout_seconds: advancedOptions.timeoutSeconds,
      },
    }),
    [advancedOptions, profile, projectId, values, workflow.id],
  )

  const summary = useMemo(() => {
    if (specState.status !== "ready") return [tForm("loading")]
    const renderable = specState.spec.fields.filter((field) => !field.platform_managed)
    const filledCount = countFilledFields(specState.spec, values)
    return [tForm("summaryFields", { filled: filledCount, total: renderable.length })]
  }, [specState, tForm, values])

  const validationMessage = useMemo(() => {
    if (specState.status === "loading") return tForm("loading")
    if (specState.status === "error") return specState.message
    if (validation.issues.length === 0) return null
    return validation.issues[0].message
  }, [specState, tForm, validation.issues])

  const canSubmit = specState.status === "ready" && validation.ok

  const handleSubmit = useCallback(async () => {
    if (!canSubmit) return
    setIsSubmitting(true)
    try {
      const { data } = await apiRequest<{ run_id: string }>("/runs", {
        method: "POST",
        body: JSON.stringify(previewPayload),
      })
      toast.success(t("toasts.runCreated"))
      onSubmitted(data.run_id)
    } catch (error) {
      toast.error(t("errors.submitFailed"), {
        description: getApiErrorMessage(error, t("errors.submitFailed")),
        duration: 8000,
      })
    } finally {
      setIsSubmitting(false)
    }
  }, [canSubmit, onSubmitted, previewPayload, t])

  const handleChange = useCallback((id: string, value: unknown) => {
    setValues((current) => ({ ...current, [id]: value }))
  }, [])

  const handleApplyImportedValues = useCallback((nextValues: FormValues) => {
    setValues((current) => ({ ...current, ...nextValues }))
    setActiveTab("form")
  }, [])

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      <RunSubmissionHeader
        workflow={workflow}
        onChangeWorkflow={onChangeWorkflow}
        onClose={onClose}
      />

      <RunSharedSettings
        projectId={projectId}
        profile={profile}
        onProfileChange={setProfile}
        advancedOptions={advancedOptions}
        onAdvancedOptionsChange={setAdvancedOptions}
      />

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        {specState.status === "loading" ? (
          <div className="text-sm text-muted-foreground">{tForm("loading")}</div>
        ) : specState.status === "error" ? (
          <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
            {specState.message}
          </div>
        ) : specState.status === "ready" ? (
          <Tabs value={activeTab} onValueChange={setActiveTab} className="gap-5">
            <TabsList>
              <TabsTrigger value="form">{t("workbench.formTab")}</TabsTrigger>
              <TabsTrigger value="input-file">{t("workbench.inputFileTab")}</TabsTrigger>
            </TabsList>
            <TabsContent value="form">
              <RunForm
                spec={specState.spec}
                projectId={projectId}
                values={values}
                onChange={handleChange}
                issues={validation.issues}
              />
            </TabsContent>
            <TabsContent value="input-file" forceMount>
              <RunInputFileImport
                spec={specState.spec}
                projectId={projectId}
                onApplyValues={handleApplyImportedValues}
              />
            </TabsContent>
          </Tabs>
        ) : null}
      </div>

      <RunSubmissionFooter
        previewOpen={previewOpen}
        summary={summary}
        validationMessage={validationMessage}
        previewPayload={previewPayload as unknown as Record<string, unknown>}
        isSubmitting={isSubmitting}
        canSubmit={canSubmit}
        onBackToPicker={onChangeWorkflow}
        onTogglePreview={() => setPreviewOpen((current) => !current)}
        onSubmit={handleSubmit}
      />
    </div>
  )
}
