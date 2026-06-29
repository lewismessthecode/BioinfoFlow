"use client"

import { type ChangeEvent, useCallback, useEffect, useRef, useState } from "react"
import { useTranslations } from "next-intl"
import { Loader2 } from "lucide-react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { cn } from "@/lib/utils"
import { apiRequest, getApiErrorMessage } from "@/lib/api"
import {
  getContainerRegistrySelectValue,
  normalizeContainerRegistries,
} from "@/lib/registry-utils"
import type { ContainerRegistryConfig, ValidateWorkflowResponse, Workflow } from "@/lib/types"
import { scrollEditorToLine } from "./workflow-code-editor"
import type { ReactCodeMirrorRef } from "@uiw/react-codemirror"

import {
  type EngineType,
  type LocalImportMode,
  type RegistrationStep,
  type SourceType,
  ALLOWED_EXTENSIONS,
  MAX_FILE_SIZE,
  useRegisterForm,
} from "./register-form-hook"
import { RegistrationProgress } from "./register-sub-components"
import { RegisterPreviewPanel } from "./register-preview-panel"
import { RegisterFormFields } from "./register-form-fields"

/* ── types ───────────────────────────────────────────────── */

interface WorkflowRegisterDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onRegistered: (workflow: Workflow) => void
}

/* ── main dialog ─────────────────────────────────────────── */

export function WorkflowRegisterDialog({
  open,
  onOpenChange,
  onRegistered,
}: WorkflowRegisterDialogProps) {
  const tWorkflows = useTranslations("workflows")
  const tCommon = useTranslations("common")
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [editorContent, setEditorContent] = useState<string | null>(null)
  const [validationResult, setValidationResult] = useState<ValidateWorkflowResponse | null>(null)
  const [isValidating, setIsValidating] = useState(false)
  const [currentStep, setCurrentStep] = useState<RegistrationStep | null>(null)
  const [imageRegistries, setImageRegistries] = useState<ContainerRegistryConfig[]>([])
  const [registriesLoaded, setRegistriesLoaded] = useState(false)
  const editorRef = useRef<ReactCodeMirrorRef>(null)
  const validateTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const form = useRegisterForm()
  const hasEditor =
    editorContent !== null &&
    form.sourceType === "local" &&
    form.localImportMode === "single-file"

  const loadImageRegistries = useCallback(async () => {
    if (registriesLoaded) {
      return
    }
    try {
      const { data } = await apiRequest<ContainerRegistryConfig[]>("/container-registries")
      setImageRegistries(normalizeContainerRegistries(data))
    } catch {
      setImageRegistries([])
    } finally {
      setRegistriesLoaded(true)
    }
  }, [registriesLoaded])

  useEffect(() => {
    if (open) {
      void loadImageRegistries()
    }
  }, [loadImageRegistries, open])

  /* ── validation ──────────────────────────────────────── */

  const validateContentWithInfo = async (
    content: string,
    engine: EngineType,
    fileName: string,
  ) => {
    setIsValidating(true)
    try {
      const { data } = await apiRequest<ValidateWorkflowResponse>("/workflows/validate", {
        method: "POST",
        body: JSON.stringify({ source: "local", engine, file_name: fileName, content }),
      })
      setValidationResult(data)
    } catch {
      // Don't block editing on network errors
    } finally {
      setIsValidating(false)
    }
  }

  const handleEditorChange = (newContent: string) => {
    setEditorContent(newContent)
    setValidationResult(null)
    if (validateTimerRef.current) clearTimeout(validateTimerRef.current)
    validateTimerRef.current = setTimeout(
      () => validateContentWithInfo(newContent, form.engine, form.localFileName),
      1000,
    )
  }

  const handleErrorClick = (line: number) => {
    scrollEditorToLine(editorRef, line)
  }

  /* ── file handling with guards ───────────────────────── */

  const handleLocalFileChangeGuarded = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    const ext = file.name.includes(".")
      ? `.${file.name.split(".").pop()?.toLowerCase()}`
      : ""
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      toast.error(tWorkflows("errors.unsupportedFileType", { ext, supported: ".wdl, .nf" }))
      event.target.value = ""
      return
    }

    if (file.size > MAX_FILE_SIZE) {
      const actualSize =
        file.size >= 1024 * 1024
          ? `${(file.size / (1024 * 1024)).toFixed(1)}MB`
          : `${(file.size / 1024).toFixed(0)}KB`
      toast.error(tWorkflows("errors.fileTooLarge", { maxSize: "50MB", actualSize }))
      event.target.value = ""
      return
    }

    form.handleLocalFileChange(event)
    const lower = file.name.toLowerCase()
    const detectedEngine: EngineType = lower.endsWith(".wdl") ? "wdl" : "nextflow"

    file.text().then((content) => {
      setEditorContent(content)
      setValidationResult(null)
      validateContentWithInfo(content, detectedEngine, file.name)
    })
  }

  /* ── source change ────────────────────────────────────── */

  const handleSourceChange = (type: SourceType) => {
    form.handleSourceChange(type)
    if (type !== "local") {
      setEditorContent(null)
      setValidationResult(null)
    }
  }

  const handleLocalImportModeChange = (mode: LocalImportMode) => {
    form.setLocalImportMode(mode)
    setCurrentStep(null)
    if (mode === "bundle") {
      setEditorContent(null)
      setValidationResult(null)
    }
  }

  /* ── reset / open change ──────────────────────────────── */

  const handleOpenChange = (nextOpen: boolean) => {
    onOpenChange(nextOpen)
    if (!nextOpen) {
      form.reset()
      setEditorContent(null)
      setValidationResult(null)
      setCurrentStep(null)
      if (validateTimerRef.current) clearTimeout(validateTimerRef.current)
    }
  }

  const handleChangeFile = () => {
    setEditorContent(null)
    setValidationResult(null)
  }

  const handleBundleDirectoryChange = (event: ChangeEvent<HTMLInputElement>) => {
    form.handleBundleDirectoryChange(event)
    setCurrentStep(null)
    setValidationResult(null)
  }

  const handleEntrypointRelpathChange = (value: string) => {
    form.setEntrypointRelpath(value)
    const lower = value.toLowerCase()
    if (lower.endsWith(".wdl")) {
      form.setEngine("wdl")
    } else if (lower.endsWith(".nf")) {
      form.setEngine("nextflow")
    }
  }

  /* ── register ─────────────────────────────────────────── */

  const handleRegister = async () => {
    if (form.sourceType === "local") {
      if (form.localImportMode === "bundle") {
        if (form.bundleFiles.length === 0) {
          toast.error(tWorkflows("errors.bundlePathRequired"))
          return
        }
        if (!form.entrypointRelpath.trim()) {
          toast.error(tWorkflows("errors.entrypointRelpathRequired"))
          return
        }
      } else if (!form.localFile && editorContent === null) {
        toast.error(tWorkflows("errors.fileRequired"))
        return
      }
    }
    if (form.sourceType !== "local" && !form.pipelineName.trim()) {
      toast.error(
        form.sourceType === "github"
          ? tWorkflows("errors.repoUrlRequired")
          : tWorkflows("errors.pipelineNameRequired"),
      )
      return
    }

    setIsSubmitting(true)
    setCurrentStep("reading")
    try {
      const payload: Record<string, unknown> = { source: form.sourceType, engine: form.engine }
      if (form.version.trim()) payload.version = form.version.trim()
      if (form.description.trim()) payload.description = form.description.trim()
      const selectedRegistryConfig = imageRegistries.find(
        (registry) => getContainerRegistrySelectValue(registry) === form.selectedRegistry.trim(),
      )
      if (selectedRegistryConfig?.id) {
        payload.container_registry_id = selectedRegistryConfig.id
      }

      if (form.sourceType === "nf-core") {
        payload.name = form.pipelineName.trim().replace(/^nf-core\//i, "")
      } else if (form.sourceType === "github") {
        payload.source_ref = form.pipelineName.trim()
      } else {
        if (form.pipelineName.trim()) payload.name = form.pipelineName.trim()
        if (form.localImportMode === "bundle") {
          const formData = new FormData()
          formData.set("engine", form.engine)
          formData.set("entrypoint_relpath", form.entrypointRelpath.trim())
          if (form.pipelineName.trim()) formData.set("name", form.pipelineName.trim())
          if (form.version.trim()) formData.set("version", form.version.trim())
          if (form.description.trim()) formData.set("description", form.description.trim())
          if (selectedRegistryConfig?.id) formData.set("container_registry_id", selectedRegistryConfig.id)
          formData.set(
            "bundle_paths",
            JSON.stringify(form.bundleFiles.map((entry) => entry.relpath)),
          )
          for (const entry of form.bundleFiles) {
            formData.append("bundle_files", entry.file)
          }

          setCurrentStep("parsing")
          await new Promise((r) => setTimeout(r, 200))
          setCurrentStep("registering")

          const { data } = await apiRequest<Workflow>("/workflows/local-bundle", {
            method: "POST",
            body: formData,
          })

          toast.success(tWorkflows("toasts.registered", { name: data.name }))
          onRegistered(data)
          handleOpenChange(false)
          return
        } else {
          const content = editorContent ?? (form.localFile ? await form.localFile.text() : null)
          payload.file_name = form.localFile?.name || form.localFileName
          payload.content = content

          if (editorContent !== null) {
            setCurrentStep("validating")
            if (!validationResult?.valid && content) {
              try {
                const { data } = await apiRequest<ValidateWorkflowResponse>("/workflows/validate", {
                  method: "POST",
                  body: JSON.stringify({ source: "local", engine: form.engine, file_name: form.localFileName, content }),
                })
                setValidationResult(data)
                if (!data.valid) {
                  toast.error(tWorkflows("errors.validationFailed"))
                  setCurrentStep(null)
                  setIsSubmitting(false)
                  return
                }
              } catch {
                // Proceed even if validation endpoint fails
              }
            }
          }
        }
      }

      setCurrentStep("parsing")
      await new Promise((r) => setTimeout(r, 200))
      setCurrentStep("registering")

      const { data } = await apiRequest<Workflow>("/workflows", {
        method: "POST",
        body: JSON.stringify(payload),
      })

      toast.success(tWorkflows("toasts.registered", { name: data.name }))
      onRegistered(data)
      handleOpenChange(false)
    } catch (error) {
      const fallbackMessage =
        form.sourceType === "local"
          ? tWorkflows("errors.registerLocalFailed")
          : tWorkflows("errors.registerFailed")
      toast.error(getApiErrorMessage(error, fallbackMessage))
    } finally {
      setIsSubmitting(false)
      setCurrentStep(null)
    }
  }

  /* ── derived labels ───────────────────────────────────── */

  let sourceLabel: string
  if (form.sourceType === "github") {
    sourceLabel = tWorkflows("registerDialog.fields.repoUrl")
  } else if (form.sourceType === "local") {
    sourceLabel = tWorkflows("registerDialog.fields.workflowNameOptional")
  } else {
    sourceLabel = tWorkflows("registerDialog.fields.pipelineName")
  }

  const sourcePlaceholder =
    form.sourceType === "github"
      ? tWorkflows("registerDialog.placeholders.repoUrl")
      : tWorkflows("registerDialog.placeholders.pipelineName")

  /* ── render ───────────────────────────────────────────── */

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className={cn(
          "overflow-hidden border-border/70 p-0 max-h-[90vh] flex flex-col",
          "sm:max-w-[min(1280px,calc(100vw-3rem))]",
        )}
      >
        <DialogHeader className="relative shrink-0 border-b border-border/60 bg-muted/30 px-6 py-4">
          <div className="pointer-events-none absolute inset-x-8 top-0 h-px bg-gradient-to-r from-transparent via-foreground/10 to-transparent" />
          <DialogTitle>{tWorkflows("registerDialog.title")}</DialogTitle>
        </DialogHeader>

        <div className="grid flex-1 items-start gap-5 overflow-y-auto px-6 py-5 xl:grid-cols-[minmax(0,1.05fr)_minmax(320px,0.95fr)]">
          <div className="space-y-4">
            <RegisterFormFields
              sourceType={form.sourceType}
              engine={form.engine}
              pipelineName={form.pipelineName}
              version={form.version}
              description={form.description}
              imageRegistries={imageRegistries}
              selectedRegistry={form.selectedRegistry}
              localImportMode={form.localImportMode}
              localFileName={form.localFileName}
              bundleLabel={form.bundleLabel}
              bundleFileCount={form.bundleFiles.length}
              entrypointCandidates={form.entrypointCandidates}
              entrypointRelpath={form.entrypointRelpath}
              sourceLabel={sourceLabel}
              sourcePlaceholder={sourcePlaceholder}
              hasEditor={hasEditor}
              editorContent={editorContent}
              editorRef={editorRef}
              isValidating={isValidating}
              validationResult={validationResult}
              onSourceChange={handleSourceChange}
              onEngineChange={form.setEngine}
              onPipelineNameChange={form.setPipelineName}
              onVersionChange={form.setVersion}
              onDescriptionChange={form.setDescription}
              onSelectedRegistryChange={form.setSelectedRegistry}
              onLocalImportModeChange={handleLocalImportModeChange}
              onLocalFileChange={handleLocalFileChangeGuarded}
              onBundleDirectoryChange={handleBundleDirectoryChange}
              onEntrypointRelpathChange={handleEntrypointRelpathChange}
              onEditorChange={handleEditorChange}
              onChangeFile={handleChangeFile}
            />

            <RegistrationProgress step={currentStep} />
          </div>

          <RegisterPreviewPanel
            pipelineName={form.pipelineName}
            localFileName={form.localFileName}
            localImportMode={form.localImportMode}
            bundleLabel={form.bundleLabel}
            bundleFileCount={form.bundleFiles.length}
            entrypointRelpath={form.entrypointRelpath}
            engine={form.engine}
            sourceType={form.sourceType}
            version={form.version}
            imageRegistries={imageRegistries}
            selectedRegistry={form.selectedRegistry}
            hasEditor={hasEditor}
            isValidating={isValidating}
            validationResult={validationResult}
            onErrorClick={handleErrorClick}
          />
        </div>

        <DialogFooter
          data-testid="workflow-register-actions"
          className="relative shrink-0 justify-end border-t border-border/60 bg-background/95 px-6 py-4"
        >
          <div className="pointer-events-none absolute inset-x-6 top-0 h-px bg-gradient-to-r from-transparent via-foreground/8 to-transparent" />
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            {tCommon("cancel")}
          </Button>
          <Button className="min-w-[140px]" onClick={handleRegister} disabled={isSubmitting}>
            {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {isSubmitting ? tWorkflows("registerDialog.submitting") : tWorkflows("register")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
